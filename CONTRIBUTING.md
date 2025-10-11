# Boston Curb SMART Grant Dev Guide

This document provides basic guidelines for developers contributing to the Boston SMART Grant Curbs Project.

## Basic Environment
To ensure maximal consistency, contributors are encouraged to using *nix-like systems. Windows users should use WSL with Ubuntu (see [Windows Subsystem for Linux](https://learn.microsoft.com/en-us/windows/wsl/install) for more information. MacOS users can contribute using their preferred bash or zsh environment.

Basic knowledge of how to navigate, manipulate, and inspect files/directories from the terminal is helpful, but advanced knowledge of Unix/Linux shell scripting shouldn't be required. If you are new to these systems or need a refresher, many guides are readily available. Here's a [cheat sheet](
https://www.datacamp.com/cheat-sheet/bash-and-zsh-shell-terminal-basics-cheat-sheet) to get started.

## Python
This project uses the latest version of Python (3.13+).

## UV
We use the [Astral UV](https://docs.astral.sh/uv/) package manager to manage Python environments dependencies. If you need to a dependency, navigate to a project directory and use:
`uv add <package id>`.

UV allows users to run scripts without directly activating an environment using `uv run`. For example, run the `main` script from `mymodule`, use:
`uv run ./mymodule/main.py` 

To activate the environment directly, you can use:
`source .venv/bin/activate` 

To deactivate the environment, simply use `deactivate`.

## Visual Studio Code
VSCode is the recommended editor for this project. 

We also recommend using the following extensions:
- WSL (Windows users only): allows VSCode to run directly from the Linux environment.
- Python: Use the official Microsoft Python language server. It comes packaged with important tooling, including environment managment and debugging. 
- Ruff: For formatting and linting. Change your workspaces to use Ruff as the default formatter if needed.
- autoDocString: For making writing [docstrings](#docstrings)

## Ruff Linting and Formatting
This project uses Ruff for linting and Black-compatible formatting. 
```sh
uv run ruff check /path/to/file --fix       # Lint all files in the current directory. 
uv run ruff format /path/to/file            # Format all files in the current directory.
```
Run these regularly as you develop, but only on files you are actively engaged in editing. Otherwise, you might pollute your commits with changes to others' work-in-progress that make code reviews more difficult. You can use the `--verbose` flag with these commands to get more explicit guidance on any errors.

If you need the linter to ignore a rule, use `# noqa: <errors to ignore, comma separated>`. Use this judiciously and always be explicit about which rules you are ignoring. For example, to bypass the enforcement of the [line too long](https://docs.astral.sh/ruff/rules/line-too-long/) rule, you could use `# noqa: E501`. See the Ruff documentation on [Rules](https://docs.astral.sh/ruff/rules/line-too-long/) for more details on error codes.

## Pre-commit
The projects makes use of the [pre-commit](https://pre-commit.com) library to ensure consistent contributions across contributors. This patches the `git commit` command with "hooks" that will run Ruff's linting and formatting procedures everytime you commit code.

To install the hooks in your local development environment, use `uv run pre-commit install` from the project's root directory.

> [!NOTE]
> - The linter/formatter may automatically change your files. Remember to re-stage and re-commit these changes before pushing.
> - Sometimes the linter will Fail, requiring you to manually fix the offending code before committing.
  
## Type Hints
Use type hinting and annotations as much as possible. MyPy provides a [helpful reference](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html) on using type hints. 
```py
# 👎no type hints
def greeting(name):
    return f"Hello, {name}!"

# 👍 Specifies both argument and return types
def greeting(name: str) -> str:
  return f"Hello, {name}!"
```

When multiple types are possible or the value of a variable of a return type is optional (i.e. it may sometimes be `None`, prefer using the modern pipe (`|`) syntax over importing and using `Union` and `Optional` from the `typing` module. For example:
```py
def get_values_if_dict(
    c: list[int] | dict[str, int]              # Instead of Union[list[str], dict[str, int]]
) -> list[int]:
    if type(c) is list:
        return c
    elif type(c) is dict:
        return list(c.values())
    raise ValueError("Expected c to be of type list or dict")

def maybe_returns(x: bool) -> str | None:       # Instead of Optional[str]
    if x:
        return "Returning a string"
    return None
```

## Docstrings
Provide docstrings on every function and method. On this project, we use [Google style](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html) docstrings. A simple example is provided below.

```py
def calculate_area(length: float, width: float) -> float:
    """Calculates the area of a rectangle.

    Args:
        length (float): The length of the rectangle.
        width (float): The width of the rectangle.

    Returns:
        float: The calculated area of the rectangle.

    Raises:
        ValueError: If length or width are negative.
    """
    if length < 0 or width < 0:
        raise ValueError("Length and width must be non-negative.")
    return length * width
```

Even if you think its completely obvious what a function is supposed to do, provide at least a simple docstring. These help to manage documentation holistically.
```py
# minimal docstring
def calculate_rmse(errors: list[int | float]) -> float:
    """Calculate root-mean-square-error loss function over a list""" 
     ...
```

As noted [above](#visual-studio-code), an a IDE extension such as autoDocString is helpful for auto-generating docstrings, including type annotations.

## GitHub

### Flow
Deveopers should roughly follow the workflows defined in [Github Flow](https://docs.github.com/en/get-started/using-github/github-flow). These are easy to use and understand, and support rapid development. The cardinal rule is simply to never commit any code directly to the `main` branch, but always to open a Pull Request from a feature branch and get approval from at least one reviewer.

```mermaid
flowchart LR
    A[Create a branch] --> B[Make changes] --> C[Open a pull request] --> D[Address comments] --> E[Merge to Main] --> F[Delete branch]
```

### Commits & Pull Requests
Individual commits should be relatively small and accompanied by a meaningful commit message with action verbs. A reviewer should be able to tell what you did by reading the commit message.
```
update contributing docs
add a function to calculate polygon area
fix typo
```

Each Pull Request and should represent a complete "feature" in the context that you are working. They will vary in size and complexity, but don't pack too many changes into a single PR. 

Make your Pull Requests easy to follow and read. Templates may be provided, but at minimum your Pull Request should include the following information:
- Description:
   - What issue(s) does this Pull Request close? Provide links.
   - Describe the core changes that were made at high level. 
- Type of Change (Feature, Bugfix, Documentation).
  - Include details about your implementation.
  - Describe any key design decisions or considerations.
  - Describe any testing or QAQC you have completed.
- QAQC / Review Notes
  - How you expect reviewers to test your changes
  - Are there actions reviewers need to take (such as re-syncing their project environment)?
- Documentation: List any documentation that you've updated as part of the PR.
- Post merge actions:
  - Any scope that needs to be tackled as a follow on task.
  - Highlight anything other contributors need to be aware of for their own work.

Make sure it is clear who is responsible for approving the changes. You should assign at least one reviewer in Github.

### Rebasing
If your feature branch falls behind `main` and you need to incorporate the latest changes, you should rebase your branch onto the `main` branch using `git rebase`. Avoid merging `main` into `your-feature`, which tends to make project history difficult to follow.
