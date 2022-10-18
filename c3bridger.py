"""
SPDX-License-Identifier: Apache-2.0
Copyright (C) 2022 Emily "TTG" Banerjee <prs.ttg+c3bridger@pm.me>
"""

# TODO: Put on pip for ease of installation & use?

from clang.cindex import *
from sys import argv, exc_info
from os.path import basename, exists
from argparse import *
from re import *
from traceback import *
from subprocess import *

# TODO: Tempfile support
bridger_parser = ArgumentParser(description = 'Process C headers into C3 interfaces')
bridger_parser.add_argument('source', metavar = 'SOURCE', type = str, nargs = 1, help = 'The C3 source file to process, or the C header to process')
bridger_parser.add_argument('--module-prefix', metavar = 'PREFIX', type = str, nargs = 1, help = 'The `::` prefix to add to emitted modules')
bridger_parser.add_argument('-I', metavar = 'PATH', action = 'append', type = str, default = [], help = 'A path on which to search for headers')
bridger_parser.add_argument('-o', metavar = 'FILE', type = str, default = '/dev/stdout', help = 'The file to output the processed source')
bridger_parser.add_argument('--odir', metavar = 'PATH', type = str, default = '.', help = 'The path at which to output generated module interfaces')
bridger_parser.add_argument('-D', metavar = 'MACRO', action = 'append', type = str, default = [], help = 'A macro definition to add to the transpilation')

bridger_args = bridger_parser.parse_args()

include_directive_pattern = compile(r'#include\s*([<"])(.+/)?([\w_]+)(\.h)([>"])\s*')

d_args = []
for d in bridger_args.D:
    d_args.append(f' -D{d}')

i_args = []
for i in bridger_args.I:
    i_args.append(f' -I{i}')

predefs = 'define C_void_t = void;\ndefine C___va_list_tag_t = void;\n'
expect_define = 0
include_processed = ''
insert_pre = None

defined_types = []

def resolve_include_file(name):
    return name

def apply_replacements(str, repls):
    for repl in repls:
        str = str.replace(repl[0], repl[1])
    return str

def define_function_ptr(type, name):
    global defined_types

    result = type.get_result()
    prototype = f'{process_type(result, result.spelling, name)}('
    for param in type.argument_types():
        if param.kind:
            prototype += f'{process_type(param, param.spelling, name)}, '
    if type.is_function_variadic():
        prototype += '...'
    prototype = prototype.rstrip(', ')
    prototype += ')'

    ret = f'define C_{name}_fptr_t = fn {prototype};'
    ret = ret.replace('(*)', '')
    ret = ret if not f'C_{name}_fptr_t' in defined_types else ''

    defined_types.append(f'C_{name}_fptr_t')

    return ret

def process_type(type, decl_name, ctx_name):
    global predefs
    global insert_pre
    global defined_types
    global nonexistent_type_replacements

    type_prefix = ''
    type_suffix = ''

    pointer_depth = 0
    type_sub = type

    array_dimensions = []

    # TODO: Need a pre-iterate for pointers due to pointer-to-array types
    while type_sub.kind == TypeKind.CONSTANTARRAY:
        array_dimensions.append(type_sub.element_count)
        type_sub = type_sub.element_type

    while type_sub.kind == TypeKind.POINTER:
        pointer_depth += 1
        type_sub = type_sub.get_pointee()

    typename = type_sub.spelling

    if type_sub.kind == TypeKind.TYPEDEF:
        type_prefix = 'C_'
        type_suffix = '' if typename.endswith('_t') else '_t'
    elif type_sub.kind == TypeKind.ELABORATED:
        type_prefix = 'C_'
        type_suffix = '' if typename.endswith('_t') else '_t'
        typename = apply_replacements(typename, [
            ['union ', ''],
            ['struct ', ''],
            ['enum ', '']
        ])

    # We need some special-case transformations here
    typename = apply_replacements(typename, [
        ['long long', 'long'],
        ['unsigned ', 'u'],
        ['uchar', 'char'],
        ['signed char', 'ichar'],
        [' signed ', ''],
        ['const ', ''],
        ['restrict ', ''],
        ['_Bool', 'bool'],
        ['const', ''],
        ['restrict', ''],
        ['long double', 'double'],
        ['__builtin_va_list', 'void']])

    if type_sub.kind == TypeKind.FUNCTIONPROTO:
        fptr = define_function_ptr(type.get_pointee(), f'{ctx_name}_{decl_name}')
        insert_pre = f'{fptr}\n'
        ret = f'C_{ctx_name}_{decl_name}_fptr_t'
        return ret

    pointers = '*' * pointer_depth
    for dim in array_dimensions:
        pointers += f'[{dim}]'
    ret = f'{type_prefix}{typename}{type_suffix}{pointers}'
    return ret

def make_enum_decl(cursor):
    # TODO: Implement enums
    name = cursor.spelling
    suffix = '' if name.endswith('_t') else '_t'
    ret = f'enum C_{name}{suffix} : int (int c_value) {{\n'
    for field in cursor.walk_preorder():
        if field.kind == CursorKind.ENUM_CONSTANT_DECL:
            ret += f'\t{field.spelling}({field.enum_value}),\n'
    ret = ret.rstrip(',\n')
    ret += '\n}\n'
    return ret

def get_struct_namespace(kind):
    namespace = ''
    if kind == CursorKind.STRUCT_DECL:
        namespace = 'struct'
    if kind == CursorKind.UNION_DECL:
        namespace = 'union'
    if kind == CursorKind.ENUM_DECL:
        namespace = 'enum'
    return namespace

qualified = compile('(struct|union|enum) (\w+)')
def make_struct_decl(cursor, name):
    global predefs
    global expect_define
    global include_processed
    global insert_pre
    global qualified
    global defined_types

    print(f'Processing struct {cursor.spelling} {name}')

    namespace = get_struct_namespace(cursor.kind)
    if cursor.kind == CursorKind.ENUM_DECL:
        return make_enum_decl(cursor)

    if not len(name):
        expect_define = len(include_processed) + len(f'{namespace} C_')

    suffix = '' if name.endswith('_t') or expect_define else '_t'
    ret = f'{namespace} C_{name}{suffix} {{\n'
    decl_count = 0
    for member in cursor.walk_preorder():
        if member.kind == CursorKind.FIELD_DECL:
            decl_count += 1
            print(f'Member of type {member.type.kind} {member.type.spelling}')
            decl = f'{process_type(member.type, member.spelling, cursor.spelling)} {member.spelling};\n'
            suffix = '' if '_t' in decl else '_t'
            decl = qualified.sub(rf'C_\2{suffix}', decl)
            ret += f'\t{decl}'
            if insert_pre:
                print(f'Adding preinsert definition {insert_pre.rstrip()}')
                include_processed = include_processed + insert_pre
                insert_pre = None
        elif member is not cursor and (member.kind == CursorKind.STRUCT_DECL or member.kind == CursorKind.UNION_DECL or member.kind == CursorKind.ENUM_DECL):
            decl_count += 1
            predefs += make_struct_decl(member, f'{name}_{get_struct_namespace(member.kind)}');
        else:
            print(f'Non-declaration member {member.kind} {member.spelling}')
    ret += '}\n'

    if not decl_count:
        ret = f'define C_{name}{suffix} = void;\n'

    ret = ret if not f'C_{name}{suffix}' in defined_types else ''

    if not len(name) and expect_define and not ret:
        expect_define = 0

    defined_types.append(f'C_{name}{suffix}')

    return ret

def resolve_header(path):
    global bridger_args

    if not exists(path):
        for incl_path in bridger_args.I:
            if exists(f'{incl_path}/{path}'):
                path = f'{incl_path}/{path}'
    
    return path

def process_header(path, module_prefix = 'c'):
    global include_directive_pattern
    global predefs
    global expect_define
    global include_processed
    global insert_pre
    global defined_types
    global qualified
    global bridger_args

    path = resolve_header(path)

    predefs = 'define C_void_t = void;\ndefine C___va_list_tag_t = void;\n'
    expect_define = 0
    include_processed = ''
    insert_pre = None
    defined_types = []

    index = Index.create()
    translation_unit = index.parse(path, args = d_args + i_args)
    cursor = translation_unit.cursor

    module_name = basename(path).replace('.h', '')
    for child in cursor.walk_preorder():
        if child.kind == CursorKind.TYPEDEF_DECL:
            suffix = '' if child.spelling.endswith('_t') else '_t'
            decl = process_type(child.underlying_typedef_type, child.spelling, '')
            decl_suffix = '' if '_t' in decl else '_t'
            decl = qualified.sub(rf'C_\2{decl_suffix}', decl)
            define_stmt = f'define C_{child.spelling}{suffix} = {decl};\n'
            if insert_pre:
                print(f'Adding preinsert definition {insert_pre.rstrip()}')
                include_processed = include_processed + insert_pre
                insert_pre = None
            if expect_define:
                include_processed = f'{include_processed[0:expect_define]}{child.spelling}{include_processed[expect_define:]}'
                expect_define = 0
            if f'C_{child.spelling}{suffix}' == f'{decl}':
                print(f'Skipping same-decL C_{child.spelling}{suffix} : {decl}')
                continue

            include_processed = include_processed + define_stmt

        elif child.kind == CursorKind.STRUCT_DECL or child.kind == CursorKind.UNION_DECL or child.kind == CursorKind.ENUM_DECL:
            decl = make_struct_decl(child, child.spelling)
            include_processed = include_processed + decl
        elif child.kind == CursorKind.FUNCTION_DECL:
            print(f'Adding function declaration {child.spelling}')
            rtype = child.type.get_result()
            ret = process_type(rtype, rtype.spelling, child.spelling)
            if insert_pre:
                print(f'Adding preinsert definition {insert_pre.rstrip()}')
                include_processed = include_processed + insert_pre
                insert_pre = None
            if expect_define:
                include_processed = f'{include_processed[0:expect_define]}{child.spelling}{include_processed[expect_define:]}'
                expect_define = 0
            prototype = '('
            fptr_n = 0
            for param in child.type.argument_types():
                pointer_depth = 0
                param_type = process_type(param, f'{fptr_n}', child.spelling)

                if insert_pre:
                    print(f'Adding preinsert definition {insert_pre.rstrip()}')
                    include_processed = include_processed + insert_pre
                    insert_pre = None
                if expect_define:
                    include_processed = f'{include_processed[0:expect_define]}{child.spelling}{include_processed[expect_define:]}'
                    expect_define = 0
                pointers = '*' * (pointer_depth - 1)
                prototype += f'{param_type}{pointers}, '
            if child.type.is_function_variadic():
                prototype += '...'
            prototype = prototype.rstrip(', ')
            prototype += ')'
            include_processed += f'fn {ret} c_{child.spelling}{prototype} @extname("{child.spelling}");\n'
        else:
            pass
            # print(f'{child.kind}: {child.spelling}')

    # This extra postprocessing is ugly but eh
    include_processed = f'{predefs}{include_processed}'
    include_processed = apply_replacements(include_processed, [['struct __va_list_tag', 'C___va_list_tag_t']]);

    with open(f'{bridger_args.odir}/{module_name}.c3i', 'w+') as h:
        h.write(f'module {module_prefix}::{module_name};\n{include_processed}')

preproc_pattern = compile(r'\n\s*#\s*.*')
seen_headers = []
def recurse_for_headers(path, contents):
    global preproc_pattern
    global seen_headers

    if path in seen_headers:
        return ''
    seen_headers.append(path)
    print(f'Recursing through {path} for preprocessor directives')
    raw = ''
    try:
        with open(resolve_header(path), 'r') as f:
            raw = f'\n{f.read()}'
            content = preproc_pattern.findall(raw)
            for r in content:
                if not '#include' in r:
                    contents += f'{r}\n'
    except:
        return f'#include "{path}"\n'
    includes = include_directive_pattern.findall(raw)
    for i in includes:
        contents += recurse_for_headers(f'{i[1]}{i[2]}{i[3]}', '')
    return contents

if bridger_args.source[0].endswith('.h'):
    process_header(bridger_args.source[0], bridger_args.module_prefix[0] if bridger_args.module_prefix else 'c')
else:
    with open(bridger_args.source[0], 'r') as f:
        source = f.read()
        out_processed = source

        # Traverse all includes
        include_directives = include_directive_pattern.findall(source)

        prefix = bridger_args.module_prefix[0] if bridger_args.module_prefix else 'c'

        # TODO: We will need to extract macros and run the preprocessor over the source aswell as inserting the declarations
        if include_directives:
            for include in include_directives:
                process_header(f'{include[1]}{include[2]}.h', prefix)
                preprocessor_dat = recurse_for_headers(f'{include[1]}{include[2]}.h', '')
                with open(f'{bridger_args.odir}/{include[2]}.h', 'w+') as h:
                    h.write(preprocessor_dat)
        
        out_processed = include_directive_pattern.sub(f'#include "{bridger_args.odir}/\\3.h"\nimport {prefix}::\\3;\n', out_processed)

        result = run(['clang', '-E', '-xc', '-'], input = bytes(out_processed, 'UTF-8'), capture_output = True)
        result = result.stdout.decode('UTF-8')
        result = preproc_pattern.sub('', f'\n{result}');

        with open(bridger_args.o, 'w+') as f:
            f.write(result)
