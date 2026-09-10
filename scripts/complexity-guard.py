#!/usr/bin/env python3
"""
complexity-guard: PostToolUse checker for C# files.

Reads the hook event JSON on stdin, inspects the file that was just written or
edited, and reports structural problems to stderr with exit 2 so Claude sees
them and fixes them before continuing.

Checks:
  - control-flow nesting depth
  - method length and parameter count (data parameters only; injected
    collaborators are not a cohesion smell)
  - file length
  - static classes that are not pure (touch time, IO, env, config, or mutable state)
  - fake async (async with no await)

Thresholds are overridable by environment variable. Test files are held to the
structural checks only; set CAG_TEST_STRICT=1 to check them like production code.
"""
import json
import os
import re
import sys

MAX_NESTING = int(os.environ.get("CAG_MAX_NESTING", 3))
MAX_METHOD_LINES = int(os.environ.get("CAG_MAX_METHOD_LINES", 40))
MAX_PARAMS = int(os.environ.get("CAG_MAX_PARAMS", 4))
MAX_FILE_LINES = int(os.environ.get("CAG_MAX_FILE_LINES", 400))
TEST_STRICT = os.environ.get("CAG_TEST_STRICT", "") not in ("", "0", "false")

SKIP_PATTERNS = (
    "/obj/", "/bin/", "/migrations/", ".g.cs", ".designer.cs",
    "globalusings.cs", "assemblyinfo.cs",
)

# Checks that a test file is exempt from. Long fixtures, a static fixture that
# mints a Guid, and a static test-data holder are all correct in test code; they
# are the same patterns that are wrong in production code.
TEST_EXEMPT = ("file_length", "impure_static", "mutable_static")

CONTROL_KEYWORDS = ("if", "else", "for", "foreach", "while", "do",
                    "switch", "try", "catch", "finally", "lock")

MODIFIER = (r"public|private|protected|internal|static|async|virtual|override|"
            r"sealed|abstract|partial|extern|new|unsafe")

# A method signature: modifier, return type, name, optional generic list, "(".
# The negative lookahead keeps type declarations and primary constructors out —
# "public class Svc(IA a)" is not a method.
METHOD_RE = re.compile(
    rf"(?:^|\s)(?:{MODIFIER})\s+"
    r"(?!class\b|record\b|struct\b|interface\b|enum\b|return\b|new\b)"
    r"[\w<>\[\],\.\?]+\s+(\w+)\s*(?:<[^<>()]*>)?\s*\("
)
CLASS_RE = re.compile(r"(?:^|\s)(?:static\s+)?(?:class|record|struct|interface)\s+(\w+)")

# Parameters supplied by the container or the framework. They are the dependency
# graph, not arguments the caller has to assemble, so they do not count toward
# the parameter budget.
DI_TYPES = {
    "CancellationToken", "HttpContext", "HttpRequest", "HttpResponse",
    "ClaimsPrincipal", "IServiceProvider", "IConfiguration", "IWebHostEnvironment",
}
DI_ATTRIBUTES = ("FromServices", "FromKeyedServices")

IMPURE = {
    "DateTime.Now": "reads the clock",
    "DateTime.UtcNow": "reads the clock",
    "DateTimeOffset.Now": "reads the clock",
    "DateTimeOffset.UtcNow": "reads the clock",
    "Guid.NewGuid": "generates identity",
    "Environment.": "reads the environment",
    "File.": "touches the file system",
    "Directory.": "touches the file system",
    "new HttpClient": "performs IO",
    "ConfigurationManager": "reads configuration",
    "Console.": "performs IO",
}

FIXES = {
    "nesting": "Invert the condition and return early. Guard clauses first, "
               "then extract the remaining block into a named method.",
    "method_length": "Extract the distinct logical steps into named private methods.",
    "params": "Group related data parameters into a record or options object. "
              "(Injected collaborators are already excluded from this count.)",
    "file_length": "Split into smaller types with one clear responsibility each.",
    "impure_static": "Make this an injectable class behind an interface owned by the "
                     "inner layer. Static is only acceptable when the method holds no "
                     "state of its own.",
    "mutable_static": "Remove the mutable static field. Shared mutable statics are not "
                      "thread-safe and break tenant isolation.",
    "fake_async": "Drop async and return the Task directly, or make the method synchronous.",
}


def strip_noise(src: str) -> str:
    """Blank out comments and string contents, preserving line structure."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            while i < n and src[i] != "\n":
                i += 1
        elif two == "/*":
            i += 2
            while i < n and src[i:i + 2] != "*/":
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            i += 2
        elif c in ('"', "'"):
            quote, i = c, i + 1
            out.append(" ")
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    i += 1
                out.append("\n" if src[i:i + 1] == "\n" else " ")
                i += 1
            i += 1
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_top_level(text: str) -> list:
    """Split a parameter list on commas that are not inside brackets."""
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return [p for p in parts if p.strip()]


def param_type(param: str) -> str:
    """The declared type of one parameter, ignoring modifiers and defaults."""
    text = param.strip()
    if text.startswith("["):
        text = text[text.rfind("]") + 1:].strip()
    depth = 0
    for i, ch in enumerate(text):
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth -= 1
        elif ch == "=" and depth == 0:
            text = text[:i]
            break
    tokens, depth, current = [], 0, ""
    for ch in text:
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth -= 1
        if ch.isspace() and depth == 0:
            if current:
                tokens.append(current)
            current = ""
        else:
            current += ch
    if current:
        tokens.append(current)
    if not tokens:
        return ""
    return tokens[-2] if len(tokens) >= 2 else tokens[-1]


def is_injected(param: str) -> bool:
    if any(a in param for a in DI_ATTRIBUTES):
        return True
    typ = param_type(param)
    if typ in DI_TYPES or typ.endswith("DbContext"):
        return True
    # Interface convention: IThing, IValidator<T>, ILogger<T>. Not "Invoice".
    return bool(re.match(r"^I[A-Z]\w*", typ))


def data_param_count(params: str) -> int:
    return sum(1 for p in split_top_level(params) if not is_injected(p))


def matching_paren(text: str, open_index: int) -> int:
    """Index of the ')' closing the '(' at open_index, or -1."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def check_params(clean: str) -> list:
    """Count data parameters on every method signature, brace-bodied or not.

    Done as its own pass over the source rather than inside the brace walker, so
    that expression-bodied members are covered too.
    """
    findings = []
    for m in METHOD_RE.finditer(clean):
        open_index = clean.index("(", m.end() - 1)
        close_index = matching_paren(clean, open_index)
        if close_index < 0:
            continue
        count = data_param_count(clean[open_index + 1:close_index])
        if count > MAX_PARAMS:
            line = clean.count("\n", 0, m.start()) + 1
            findings.append((line, "params",
                             f"{m.group(1)}() takes {count} data parameters "
                             f"(limit {MAX_PARAMS})"))
    return findings


def analyse(src: str, is_test: bool) -> list:
    findings = []
    lines = src.splitlines()
    clean = strip_noise(src)
    clean_lines = clean.splitlines()

    if len(lines) > MAX_FILE_LINES:
        findings.append((len(lines), "file_length",
                         f"file is {len(lines)} lines (limit {MAX_FILE_LINES})"))

    findings.extend(check_params(clean))

    stack, buf, line = [], "", 1
    for ch in clean:
        if ch == "\n":
            line += 1
            buf += " "
            continue
        if ch == "{":
            # A brace inside an unclosed argument or parameter list is a
            # collection or object initializer, not a body. Keep the pending
            # statement so the real body brace still sees its signature.
            if buf.count("(") > buf.count(")"):
                stack.append({"kind": "initializer", "name": "", "start": line,
                              "pending": buf})
                buf = ""
                continue

            stmt = " ".join(buf.split())
            kind, name, extra = "block", "", {}
            head = stmt.split("(")[0].strip()
            if any(re.search(rf"(^|\W){k}(\W|$)", head) for k in CONTROL_KEYWORDS):
                kind = "control"
            elif CLASS_RE.search(stmt) and "(" not in stmt.split("class")[0]:
                m = CLASS_RE.search(stmt)
                kind, name = "type", m.group(1)
                extra["static"] = bool(re.search(r"\bstatic\b", stmt))
            else:
                m = METHOD_RE.search(stmt)
                # "=> " after the signature means this brace opens an expression
                # body's initializer or lambda, not the method's own block.
                if m and "=>" not in stmt[m.end() - 1:]:
                    kind, name = "method", m.group(1)
                    extra["async"] = bool(re.search(r"\basync\b", stmt))

            if kind == "control":
                depth = sum(1 for f in stack if f["kind"] == "control") + 1
                if depth > MAX_NESTING:
                    findings.append((line, "nesting",
                                     f"control flow nested {depth} deep (limit {MAX_NESTING})"))

            stack.append({"kind": kind, "name": name, "start": line, **extra})
            buf = ""
            continue
        if ch == "}":
            if stack:
                frame = stack.pop()
                if frame["kind"] == "initializer":
                    buf = frame["pending"] + " "
                    continue
                span = line - frame["start"]
                body = "\n".join(clean_lines[frame["start"] - 1:line])
                if frame["kind"] == "method":
                    if span > MAX_METHOD_LINES:
                        findings.append((frame["start"], "method_length",
                                         f"{frame['name']}() is {span} lines "
                                         f"(limit {MAX_METHOD_LINES})"))
                    if frame.get("async") and not re.search(r"\bawait\b", body):
                        findings.append((frame["start"], "fake_async",
                                         f"{frame['name']}() is async but never awaits"))
                if frame["kind"] == "type" and frame.get("static"):
                    for token, why in IMPURE.items():
                        if token in body:
                            findings.append((frame["start"], "impure_static",
                                             f"static class {frame['name']} {why} "
                                             f"via {token.rstrip('.')}"))
                            break
                    if re.search(r"\bstatic\s+(?!readonly|const)[\w<>\[\],\.\?]+\s+\w+\s*(=|;)",
                                 body):
                        findings.append((frame["start"], "mutable_static",
                                         f"static class {frame['name']} holds mutable "
                                         f"static state"))
            buf = ""
            continue
        if ch == ";":
            buf = ""
            continue
        buf += ch

    if is_test and not TEST_STRICT:
        findings = [f for f in findings if f[1] not in TEST_EXEMPT]

    return sorted(set(findings))


def is_test_path(norm: str) -> bool:
    low = norm.lower()
    return ("/tests/" in low or "/test/" in low
            or low.endswith("tests.cs") or low.endswith("test.cs"))


def relative(path: str) -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        return os.path.relpath(path, root)
    except ValueError:
        # A different drive on Windows has no relative form.
        return path


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    path = (event.get("tool_input") or {}).get("file_path", "")
    # Hook events carry native separators; the skip list is written with "/".
    norm = path.replace("\\", "/").lower()
    if not norm.endswith(".cs") or any(p in norm for p in SKIP_PATTERNS):
        return 0
    if not os.path.isfile(path):
        return 0

    try:
        src = open(path, encoding="utf-8-sig").read()
    except Exception:
        return 0

    findings = analyse(src, is_test_path(norm))
    if not findings:
        return 0

    rel = relative(path)
    print(f"complexity-guard: {len(findings)} issue(s) in {rel}", file=sys.stderr)
    seen = set()
    for line, kind, msg in findings[:12]:
        print(f"  {rel}:{line} - {msg}", file=sys.stderr)
        if kind not in seen:
            print(f"      fix: {FIXES[kind]}", file=sys.stderr)
            seen.add(kind)
    print("Fix these before continuing. If a threshold is genuinely wrong for this "
          "code, say so and ask - do not work around the check.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
