# C3 Bridger
*A C header to C3 interface transpiler*

C3 Bridger does exactly what it says on the tin, it converts C headers to C3 interfaces - and can even create transformations of C3 code containing `#include` statements to prevent preprocessor erasure and make the workflow easier (this has the side effect of enabling C preprocessor use in C3 - make of this what you will).

## Prerequisites

I have only tested C3 Bridger with Python 3.10, but it's likely that slightly older versions of Python 3 will work fine.

Package wise C3 Bridger uses the libclang cindex bindings for Python, which can be installed using `pip3 install libclang` or `python3 -m pip install clang` if you are having trouble with multiple python installations.

## Usage

A demo application showing the usage of a C3 Bridger processed module can be seen in `demo/`. To build this demo, run:
```
python3 c3bridger.py -o out/test.c3 --odir out demo/test.c3 -Idemo
c3c compile out/test.c3 out/*.c3i --obj-out out
```

To generate a module from a single header, run:
```
python3 c3bridger.py my_header.h -o my_module.c3i
```

C3 bridger infers that a file is a C header using the `.h` prefix. Header files not ending in `.h` are not currently supported.

For more information on the CLI - consult `--help`.

## Preprocessor Settings

*C3 Bridger **DOES NOT** inherit implicit defines and include paths from your compiler or installation - if things aren't working correctly ensure **all** preprocessor settings (such as seen via. `clang -v`) are copied via. the `-I` and `-D` flags*

The include paths passed to C3 Bridger are used for header resolution in all cases (including CLI files), following their order of passing on the CLI.
