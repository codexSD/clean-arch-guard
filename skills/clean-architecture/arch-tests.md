# Mechanical boundary enforcement (.NET)

A rule that is not in CI is a suggestion. Add one test project that fails the build when the
dependency rule is broken.

```bash
dotnet add tests/Architecture.Tests package NetArchTest.Rules
```

```csharp
public class DependencyRuleTests
{
    private const string Domain = "Company.Product.Domain";
    private const string Application = "Company.Product.Application";
    private const string Infrastructure = "Company.Product.Infrastructure";
    private const string Api = "Company.Product.Api";

    [Fact]
    public void Domain_depends_on_nothing()
    {
        var result = Types.InAssembly(typeof(DomainMarker).Assembly)
            .Should().NotHaveDependencyOnAny(Application, Infrastructure, Api)
            .GetResult();

        Assert.True(result.IsSuccessful, Describe(result));
    }

    [Fact]
    public void Application_does_not_depend_on_outer_layers()
    {
        var result = Types.InAssembly(typeof(ApplicationMarker).Assembly)
            .Should().NotHaveDependencyOnAny(Infrastructure, Api)
            .GetResult();

        Assert.True(result.IsSuccessful, Describe(result));
    }

    [Fact]
    public void Domain_is_free_of_persistence_and_framework_types()
    {
        var result = Types.InAssembly(typeof(DomainMarker).Assembly)
            .Should().NotHaveDependencyOnAny(
                "Microsoft.EntityFrameworkCore",
                "Microsoft.AspNetCore",
                "Microsoft.Extensions.DependencyInjection",
                "System.Text.Json",
                "Newtonsoft.Json")
            .GetResult();

        Assert.True(result.IsSuccessful, Describe(result));
    }

    [Fact]
    public void Entities_are_sealed_or_explicitly_extensible()
    {
        var result = Types.InAssembly(typeof(DomainMarker).Assembly)
            .That().Inherit(typeof(Entity))
            .Should().BeSealed()
            .GetResult();

        Assert.True(result.IsSuccessful, Describe(result));
    }

    private static string Describe(TestResult result) =>
        result.IsSuccessful
            ? string.Empty
            : "Violations: " + string.Join(", ", result.FailingTypeNames);
}
```

Add a marker interface or empty class per project (`DomainMarker`, `ApplicationMarker`) so the tests
reference assemblies without hardcoding names.

Wire it into CI so the build fails, not just the local run:

```yaml
- run: dotnet test tests/Architecture.Tests --no-build -v minimal
```

Extend with project-specific rules as violations appear — one test per rule the team actually had
to enforce. Do not add speculative rules.
