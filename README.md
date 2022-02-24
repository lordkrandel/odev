# odev
Helps you develop Odoo

```
$ ocli --help
Usage: ocli [OPTIONS] COMMAND [ARGS]...

Commands:
  checkout          Git-checkouts multiple repositories.
  create            Create a new workspace from a series of selections.
  db-clear          Clear database by dropping and recreating it.
  db-dump           Dump the DB for the selected workspace.
  db-init           Initialize the database, with modules and hook.
  db-restore        Restore the DB for the selected workspace.
  delete-project    Delete a project.
  delete-workspace  Delete a workspace.
  fetch             Git-fetches multiple repositories.
  hook              Display or edit the post_hook python file.
  load              Load given workspace into the session.
  project           Display project data for the current folder.
  projects          Display all the available project folders.
  pull              Git-pulls selected repos for current workspace.
  push              Git-pushes multiple repositories.
  rc                View or edit the .odoorc config with default editor.
  setup             Sets up the main folder, with repos and venv.
  shell             Starts Odoo as an interactive shell.
  start             Start Odoo and reinitialize the workspace's modules.
  start-tests       Start Odoo with the tests-enable flag on.
  status            Display status for all repos for current workspace.
  workspace         Display currently selected workspace data.
  workspaces        Display all the available workspaces for current project.
```
