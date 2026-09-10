#!/usr/bin/env python3
"""
Regression tests for complexity-guard.

Each case is C# source plus the set of finding kinds it must produce. Run:

    python3 tests/test_complexity_guard.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, os.pardir, "scripts", "complexity-guard.py")

spec = importlib.util.spec_from_file_location("guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def kinds(src, is_test=False):
    return sorted({k for _, k, _ in guard.analyse(src, is_test)})


CASES = []


def case(name, expected, src, is_test=False):
    CASES.append((name, expected, src, is_test))


# --- nesting ---------------------------------------------------------------

case("nesting over limit", ["nesting"], """
public class C {
    public void M(int x) {
        if (x > 0) {
            foreach (var i in items) {
                while (x > 0) {
                    if (x == 1) { x--; }
                }
            }
        }
    }
}
""")

case("nesting counted through a collection expression in the header", ["nesting"], """
public class C {
    public void M(int x) {
        if (x > 0) {
            foreach (var i in new[] { 1, 2 }) {
                while (x > 0) {
                    if (x == 1) { x--; }
                }
            }
        }
    }
}
""")

case("nesting at the limit is clean", [], """
public class C {
    public void M(int x) {
        if (x > 0) {
            foreach (var i in items) {
                while (x > 0) { x--; }
            }
        }
    }
}
""")

# --- parameters ------------------------------------------------------------

case("five data parameters", ["params"], """
public class C {
    public void M(int a, string b, decimal c, Guid d, DateTime e) { }
}
""")

case("injected collaborators do not count", [], """
public static class RequestOtp {
    public static async Task<IResult> HandleAsync(
        OtpRequest request,
        HttpContext http,
        IOtpService otp,
        IValidator<OtpRequest> validator,
        ILoggerFactory loggers,
        CancellationToken ct)
    {
        await otp.RequestAsync(request, ct);
        return Results.Accepted();
    }
}
""")

case("a DbContext does not count", [], """
public class C {
    public void M(Guid id, AppDbContext db, IClock clock, CancellationToken ct) { }
}
""")

case("[FromServices] does not count", [], """
public class C {
    public void M(Guid a, Guid b, [FromServices] Thing t, [FromServices] Other o) { }
}
""")

case("generic method parameters are counted", ["params"], """
public class C {
    public void G<T>(int a, int b, int c, int d, int e) where T : class { }
}
""")

case("expression-bodied method parameters are counted", ["params"], """
public class C {
    public int Add(int a, int b, int c, int d, int e) => a + b + c + d + e;
}
""")

case("a primary constructor is not a method", [], """
public class Svc(IA a, IB b, IC c, ID d, IE e, IF f) {
    public int Get() => 1;
}
""")

case("a positional record is not a method", [], """
public record Dto(int A, string B, decimal C, Guid D, DateTime E, bool F);
""")

# --- fake async ------------------------------------------------------------

case("async with no await", ["fake_async"], """
public class C {
    public async Task M() { return; }
}
""")

case("await only in a string does not count", ["fake_async"], """
public class C {
    public async Task M() { var s = "await me"; }
}
""")

case("await only in a comment does not count", ["fake_async"], """
public class C {
    public async Task M() {
        // await me
        return;
    }
}
""")

case("real await is clean", [], """
public class C {
    public async Task M() { await Task.Delay(1); }
}
""")

case("expression-bodied async with an anonymous object is clean", [], """
public class C {
    private async Task<X> LoginAsync(string id) =>
        await client
            .PostAsJsonAsync("/login", new { id, pw = Pw });
}
""")

# --- statics ---------------------------------------------------------------

case("static class reading the clock", ["impure_static"], """
public static class Clocky {
    public static DateTime When() { return DateTime.UtcNow; }
}
""")

case("static class with mutable state", ["mutable_static"], """
public static class Cachey {
    private static int _count = 0;
    public static void Bump() { _count++; }
}
""")

case("pure static class is clean", [], """
public static class PureMath {
    public static int Twice(int x) { return x * 2; }
}
""")

case("static readonly is not mutable state", [], """
public static class Ok {
    private static readonly int Limit = 5;
    public static int Get() { return Limit; }
}
""")

case("a test fixture may mint identity", [], """
public static class TestClient {
    public static string NewPhone() { return Guid.NewGuid().ToString(); }
}
""", is_test=True)

case("the same fixture is flagged in production code", ["impure_static"], """
public static class TestClient {
    public static string NewPhone() { return Guid.NewGuid().ToString(); }
}
""")

# --- length ----------------------------------------------------------------

case("long method", ["method_length"], """
public class C {
    public void M() {
""" + "\n".join(f"        var x{i} = {i};" for i in range(45)) + """
    }
}
""")

case("long file", ["file_length"], "// x\n" * 401)

case("a long test file is not flagged", [], "// x\n" * 401, is_test=True)


def main():
    failures = []
    for name, expected, src, is_test in CASES:
        actual = kinds(src, is_test)
        if actual != sorted(expected):
            failures.append((name, sorted(expected), actual))

    for name, expected, actual in failures:
        print(f"FAIL {name}\n     expected {expected}\n     actual   {actual}")

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
