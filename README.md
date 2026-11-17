Original project: https://github.com/atomizer/sbpe
# StarBreak Plugin Engine (SBPE) for Linux

This Linux-only fork adapts SBPE to the native Linux version of StarBreak.
The Windows loader and prebuilt Windows runtime are not included.
Currently tested on Ubuntu-based distributions.

## Linux build
NOTE: This project was tested with Python 3.14 only.

### Install the dependencies
```
sudo apt install build-essential binutils libsdl2-dev python3.14-dev python3.14-venv python3-venv
```
Open a terminal pointing to the root folder of the project and create a venv:
```
python3 -m venv venv
source venv/bin/activate
```
Install the dependencies of the project:
```
pip install -r requirements-linux.txt
```
Then, execute the `rbp_buider.py` and `buider.py`:
```
cd rectbinpack
python rbp_builder.py
cd ..
python builder.py
```
Deactivate the venv:
```
deactivate
```
That's all, sbpe is ready to go.

## How to run
Open a terminal in the root folder, activate the venv and then execute `loader.py`:
```
source venv/bin/activate
python loader.py
```

## License
All terms and licenses applicable to the original project apply to that project as well.
