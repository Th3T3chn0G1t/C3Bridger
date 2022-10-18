import std::io;

#include "test.h"
#include <stdio.h>
#include <string.h>

fn void main() {
    io::println("Hello, C3 world!");
    stdio::c_printf("Hello, C world!\n");

    char* a = TEST_AAA;
    char* b = "bar";
    char[$sizeof(a) + $sizeof(b) - 1] c = {};
    string::c_strcpy(&c, a);
    string::c_strcat(&c, b);
    stdio::c_printf("%s\n", &c);
}
