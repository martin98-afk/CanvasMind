pyinstaller --onedir --add-data "app;app" --add-data "logo.png;logo.png" --add-data "envs/Miniconda3-py311_23.11.0-2-Windows-x86_64.exe;envs" --add-data ".venv/Lib/site-packages/spyder;spyder" --add-data "resource;resource" --add-data "examples;examples" --copy-metadata jupyter_client --hidden-import jupyter_client.provisioning.local --hidden-import ipykernel -i logo.png --windowed main.py


python -m nuitka --standalone --include-data-dir=app=app --include-data-file=logo.png=logo.png --include-data-dir=envs=envs --include-data-dir=D:/work/NarratoAI/venv\Lib/site-packages/spyder=spyder   --include-data-dir=resource=resource   --include-data-dir=examples=examples --windows-disable-console   --windows-icon-from-ico=logo.png   main.py


pyinstaller --onedir --add-data "app;app" --add-data "venv\Lib\site-packages\spyder;spyder" --add-data "venv\Lib\site-packages\pyecharts;pyecharts" --add-data "venv\Lib\site-packages\prettytable;prettytable" --add-data "resource;resource" --add-data "examples;examples" --copy-metadata jupyter_client --hidden-import jupyter_client.provisioning.local --hidden-import ipykernel -i ./icons/logoico.ico --windowed main.py
