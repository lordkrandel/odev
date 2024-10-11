# odev

Helps you develop Odoo.

## setup

```bash
ocli setup
```

Sets up a folder with all the Odoo repos you need (making it a `project` folder).

![image](https://github.com/user-attachments/assets/72e8ec30-ac7e-401b-810b-4edd35c3483f)

## workspace

```bash
ocli workspace <workspace_name>
```

Prints the content of the given `workspace` (default: current), and shows the
list of available `workspaces` for the project.

![image](https://github.com/user-attachments/assets/5b217f5d-4a0b-4496-8036-0009b8ca7524)

## workspaces

```bash
ocli workspaces
```

Shows the list of available `workspaces` for the project.

![image](https://github.com/user-attachments/assets/1df6be3c-340b-46aa-a4e7-0746456358b1)

## workspace-from-pr

```bash
ocli workspace-from-pr <pr_number>
```

Creates a full `workspace` from any Odoo PR.

![image](https://github.com/user-attachments/assets/c27796a0-f025-40e1-8757-8e238ba2ef32)

## load

```bash
ocli load <pr_number>
```

Checks out the branches from all `repo`s that compose the `workspace`.
You can only change `workspace` if there are no changes in your working copies.

![image](https://github.com/user-attachments/assets/16420986-eb53-450d-b0bb-2699b1782b7d)

## projects, project

```bash
ocli projects
ocli project
```

Shows informations about all `project`s, and the detail about the current one.

Projects are folders containing your repos, their configuration is represented by a folder
under $XDG_CONFIG, and in turn they contain folders, one for each `workspace`.

![image](https://github.com/user-attachments/assets/244b0c6f-9e78-49f4-b24a-e1abc2fa08c8)

## update

```bash
ocli update <workspace_name>
```

Loads a `workspace`, `fetch`es all repositories, pulls them all, and reloads the old `workspace` back.

![image](https://github.com/user-attachments/assets/0b23be01-1ff5-4b3d-80fb-3adf98c03b6b)

## help

... and there are many more commands!

```
~/projects/odev $ ocli --help
                                                                                                                                                                                                                   
 Usage: ocli [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                           
                                                                                                                                                                                                                   
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --install-completion          Install completion for the current shell.                                             │
│ --show-completion             Show completion for the current shell, to copy it or customize the installation.      │
│ --help                        Show this message and exit.                                                           │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ──────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ activate-path       Path to the activate script for the current virtual environment.                                │
│ checkout            Git-checkouts multiple repositories.                                                            │
│ db-clear            Clear database by dropping and recreating it.                                                   │
│ db-dump             Dump the DB for the selected workspace.                                                         │
│ db-init             Initialize the database, with modules and hook.                                                 │
│ db-restore          Restore the DB for the selected workspace.                                                      │
│ deps                Find module dependancy order for a specific module.                                             │
│ diff                Git-diffs all repositories.                                                                     │
│ external-tests      Init db and run Odoo's external tests. This will install the demo data.                         │
│ fetch               Git-fetches multiple repositories.                                                              │
│ hook                Display or edit the post_hook python file.                                                      │
│ hub                 Open Github in a browser on a branch of a given repo.                                           │
│ init-tests          Init db and run Odoo's at_install tests. This will install the demo data.                       │
│ l10n-tests          Run l10n tests                                                                                  │
│ lint                Start linting tests.                                                                            │
│ load                Load given workspace into the session.                                                          │
│ post-tests          Init db (if not fast) and run Odoo's post_install tests. This will install the demo data.       │
│ project             Display project data for the current folder.                                                    │
│ project-create      Create a project for the current directory                                                      │
│ project-delete      Delete a project.                                                                               │
│ projects            Display all the available project folders.                                                      │
│ pull                Git-pulls selected repos for current workspace.                                                 │
│ push                Git-pushes multiple repositories.                                                               │
│ rc                  View or edit the .odoorc config with default editor.                                            │
│ runbot              Open runbot in a browser for current bundle.                                                    │
│ setup               Sets up the main folder, with repos and venv.                                                   │
│ setup-requisites    Setup a Python virtual environment for the project.                                             │
│ shell               Starts Odoo as an interactive shell.                                                            │
│ start               Start Odoo and reinitialize the workspace's modules.                                            │
│ status              Display status for all repos for current workspace.                                             │
│ test                Initialize db and run all tests, but the external ones.                                         │
│ update              Updates given workspace and reloads the current one.                                            │
│ upgrade             Run upgrade from a old Workspace to a new Workspace ex. ocli upgrade 15.0 15.0-account-myfix    │
│ workspace           Display currently selected workspace data.                                                      │
│ workspace-create    Create a new workspace from a series of selections.                                             │
│ workspace-delete    Delete a workspace.                                                                             │
│ workspace-dupe      Duplicate a workspace.                                                                          │
│ workspace-from-pr   Requires `gh` to be installed (Github CLI) Creates a                                            │
│                     workspace from a PR number on odoo/odoo or odoo/enterprise.                                     │
│                     If `load` is specified, it also loads generated workspace.                                      │
│ workspace-move      Renames a workspace.                                                                            │
│ workspace-set       Change the current workspace without loading it                                                 │
│ workspaces          Display all the available workspaces for current project.                                       │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
