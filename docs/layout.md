# Layout

The files that every repository of the template's general shape holds are laid out once, in
sdk-template's README,
[The general part of a repository](https://github.com/xippios/sdk-template/blob/main/README.md#the-general-part-of-a-repository).
This file holds what `xippios-mcp` adds to them, a module, a script or a test of
its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.mcp` (sdk-core ADR-0006); `src/xippios/` is a
namespace package.

<!-- What this package adds to those files, in a code block laid out as the family's tree is: a line per file or directory with what it holds, the package's own modules, scripts and tests among them. -->
