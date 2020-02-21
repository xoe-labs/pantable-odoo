#!/usr/bin/env python

r"""Panflute filter to parse CSV table in fenced YAML code blocks."""

import csv
import fractions
import io

import panflute
import odoolib


class EmptyTableError(Exception):
    pass

class MoreThanHeaderContentError(Exception):
    pass


def get_width(options, n_col):
    """parse `options['width']` if it is list of non-negative numbers
    else return None.
    """
    if 'width' not in options:
        return

    width = options['width']

    if len(width) != n_col:
        panflute.debug("pantable: given widths different from no. of columns in the table.")
        return

    try:
        width = [float(fractions.Fraction(x)) for x in width]
    except ValueError:
        panflute.debug("pantable: specified width is not valid number or fraction and is ignored.")
        return

    for width_i in width:
        if width_i < 0.:
            panflute.debug("pantable: width cannot be negative.")
            return

    return width


def get_table_width(options):
    """parse `options['table-width']` if it is positive number
    else return 1.
    """
    if 'table-width' not in options:
        return 1.

    table_width = options['table-width']

    try:
        table_width = float(fractions.Fraction(table_width))
    except ValueError:
        panflute.debug("pantable: table width should be a number or fraction. Set to 1 instead.")
        return 1.

    if table_width <= 0.:
        panflute.debug("pantable: table width must be positive. Set to 1 instead.")
        return 1.

    return table_width


def auto_width(table_width, n_col, table_list):
    """Calculate width automatically according to length of cells.
    Return None if table is empty.
    """
    # calculate max line width per column
    max_col_width = [
        max(
            max(map(len, row[j].split("\n")))
            for row in table_list
        )
        for j in range(n_col)
    ]

    width_tot = sum(max_col_width)

    if width_tot == 0:
        raise EmptyTableError

    # The +3 match the way pandoc handle width, see jgm/pandoc commit 0dfceda
    scale = table_width / (width_tot + 3 * n_col)
    return [(width + 3) * scale for width in max_col_width]


def parse_alignment(alignment_string, n_col):
    """
    `alignment` string is parsed into pandoc format (AlignDefault, etc.).
    Cases are checked:

    - if not given, return None (let panflute handle it)
    - if wrong type
    - if too long
    - if invalid characters are given
    - if too short
    """
    align_dict = {
        'l': "AlignLeft",
        'c': "AlignCenter",
        'r': "AlignRight",
        'd': "AlignDefault"
    }

    def get(key):
        '''parsing alignment'''
        key_lower = key.lower()
        if key_lower not in align_dict:
            panflute.debug("pantable: alignment: invalid character {} found, replaced by the default 'd'.".format(key))
            key_lower = 'd'
        return align_dict[key_lower]

    # alignment string can be None or empty; return None: set to default by
    # panflute
    if not alignment_string:
        return

    # test valid type
    if not isinstance(alignment_string, str):
        panflute.debug("pantable: alignment should be a string. Set to default instead.")
        # return None: set to default by panflute
        return

    n = len(alignment_string)

    if n > n_col:
        alignment_string = alignment_string[:n_col]
        panflute.debug("pantable: alignment string is too long, truncated.")

    alignment = [get(key) for key in alignment_string]

    # fill up with default if too short
    if n < n_col:
        alignment += ["AlignDefault"] * (n_col - n)

    return alignment


def read_data(url, port, database, login, password, model, fields, domain, firstrow=None):
    """Read an odoo model.

    `url`: URL of the odoo instance.

    `database`: name of the database.

    `model`: name of the odoo model in dot-notaion (ej `res.partner`).

    `fields`: list of field names.

    `domain`: list of tuples with odoo domain expression.

    `firstrow`: string overriding odoo's header row.

    Returns list (rows) of lists (columns) of the fetched data.
    """
    connection = odoolib.get_connection(
        hostname=url,
        port=port,
        database=database,
        login=login,
        password=password,
    )
    connection.get_user_context()
    model = connection.get_model(model)
    ids = model.search(domain)
    table_list = model.export_data(
        ids,
        fields,
        context=dict(connection.user_context or {}, import_compat=False)
    )["datas"]

    if not table_list:
        raise EmptyTableError

    if firstrow:
        with io.StringIO(firstrow) as f:
            rows = [row for row in csv.reader(f)]
            if not len(rows) == 1:
                raise MoreThanHeaderContentError
            table_list.insert(0, rows[0])
    return table_list


def regularize_table_list(raw_table_list):
    """When the length of rows are uneven, make it as long as the longest row.

    `raw_table_list` modified inplace.

    return `n_col`
    """
    length_of_rows = [len(row) for row in raw_table_list]
    n_col = max(length_of_rows)

    for i, (n, row) in enumerate(zip(length_of_rows, raw_table_list)):
        if n != n_col:
            row += [''] * (n_col - n)
            panflute.debug("pantable: the {}-th row is shorter than the longest row. Empty cells appended.".format(i))
    return n_col


def parse_table_list(markdown, table_list):
    """read table in list and return panflute table format
    """

    def markdown_to_table_cell(string):
        return panflute.TableCell(*panflute.convert_text(string))

    def plain_to_table_cell(string):
        return panflute.TableCell(panflute.Plain(panflute.Str(string)))

    to_table_cell = markdown_to_table_cell if markdown else plain_to_table_cell

    return [panflute.TableRow(*map(to_table_cell, row)) for row in table_list]


def get_width_wrap(options, n_col, table_list):
    # parse width
    width = get_width(options, n_col)
    # auto-width when width is not specified
    if width is None:
        width = auto_width(get_table_width(options), n_col, table_list)
    return width


def get_caption(options):
    '''parsed as markdown into panflute AST if non-empty.'''
    return panflute.convert_text(str(options['caption']))[0].content if 'caption' in options else None


def modified_align_border(text, alignment, header):
    '''Modify the alignment border row to include pandoc
    alignment syntax
    '''
    align_dict = {
        'AlignLeft': [0],
        'AlignCenter': [0, -1],
        'AlignRight': [-1],
        'AlignDefault': []
    }

    def modify_border(header_border, alignment):
        header_border = list(header_border)
        idxs = align_dict[alignment]
        for idx in idxs:
            header_border[idx] = ':'
        return ''.join(header_border)

    text_list = text.split('\n')

    # walk to the header border
    if header:
        found = False
        for i, line in enumerate(text_list):
            if set(line) == {'+', '='}:
                found = True
                break
        if not found:
            panflute.debug('pantable: cannot add alignment to grid table.')
    else:
        i = 0

    # modify the line corresponding to the alignment border row
    header_border = text_list[i]

    header_border_list = header_border.split('+')[1:-1]

    header_border_list = [
        modify_border(header_border_i, alignment_i)
        for header_border_i, alignment_i in zip(header_border_list, alignment)
    ]

    text_list[i] = '+{}+'.format('+'.join(header_border_list))

    return '\n'.join(text_list)


def csv_to_grid_tables(table_list, caption, alignment, header):
    try:
        import terminaltables
    except ImportError:
        panflute.debug('pantable: terminaltables not found. Please install by `pip install terminaltables`.')
        raise

    table = terminaltables.AsciiTable(table_list)
    table.inner_row_border = True
    if header:
        table.CHAR_H_INNER_HORIZONTAL = '='
    text = table.table

    if alignment:
        text = modified_align_border(text, alignment, header)
    if caption:
        text += '\n\n: {}'.format(caption)
    return text


def csv_to_pipe_tables(table_list, caption, alignment):
    align_dict = {
        "AlignLeft": ':---',
        "AlignCenter": ':---:',
        "AlignRight": '---:',
        "AlignDefault": '---'
    }

    table_list.insert(1, [align_dict[key] for key in alignment])
    pipe_table_list = ['|\t{}\t|'.format('\t|\t'.join(map(str, row))) for row in table_list]
    if caption:
        pipe_table_list.append('')
        pipe_table_list.append(': {}'.format(caption))
    return '\n'.join(pipe_table_list)


def odoo2table_markdown(options, data, use_grid_tables):
    """Construct pipe/grid table directly.
    """
    # prepare table in list from data/include
    table_list = read_data(
        options.get('url'),
        options.get('port', 80),
        options.get('database', options.get('url')),
        options.get('login'),
        options.get('password'),
        options.get('model'),
        options.get('fields'),
        options.get('domain', []),
        firstrow=data,
    )

    # regularize table: all rows should have same length
    n_col = regularize_table_list(table_list)

    # parse alignment
    alignment = parse_alignment(options.get('alignment', None), n_col)
    del n_col
    # get caption
    caption = options.get('caption', None)

    text = csv_to_grid_tables(
        table_list, caption, alignment,
        (len(table_list) > 1 and options.get('header', True))
    ) if use_grid_tables else csv_to_pipe_tables(
        table_list, caption, alignment
    )

    raw_markdown = options.get('raw_markdown', False)
    if raw_markdown:
        # TODO: change this to 'markdown' once the PR accepted:
        # for now since pandoc treat all raw html as markdown it
        # will still works
        # https://github.com/sergiocorreia/panflute/pull/103
        return panflute.RawBlock(text, format='html')
    else:
        return panflute.convert_text(text)


def odoo2table_ast(options, data):
    """provided to panflute.yaml_filter to parse its content as pandoc table.
    """
    # prepare table in list from data/include
    table_list = read_data(
        options.get('url'),
        options.get('port', 80),
        options.get('database', options.get('url')),
        options.get('login'),
        options.get('password'),
        options.get('model'),
        options.get('fields'),
        options.get('domain', []),
        firstrow=data,
    )

    # regularize table: all rows should have same length
    n_col = regularize_table_list(table_list)

    # Initialize the `options` output from `panflute.yaml_filter`
    width = get_width_wrap(options, n_col, table_list)

    # parse list to panflute table
    table_body = parse_table_list(
        options.get('markdown', False),
        table_list
    )
    del table_list
    # extract header row
    header_row = table_body.pop(0) if (
        len(table_body) > 1 and options.get('header', True)
    ) else None

    # parse alignment
    alignment = parse_alignment(options.get('alignment', None), n_col)
    del n_col
    # get caption
    caption = get_caption(options)

    return panflute.Table(
        *table_body,
        caption=caption,
        alignment=alignment,
        width=width,
        header=header_row
    )


def convert2table(options, data, element, doc):

    global_options = doc.get_metadata('odootable', {})

    if 'url' not in options:
        assert global_options.get("url"), "URL must be set either globally or locally"
        options["url"] = global_options.get("url")
        if 'database' not in options:
            options["database"] = (
                global_options.get("database") or global_options.get("url")
            )

    if 'database' not in options:
        options["database"] = options.get('url')

    if 'port' not in options:
        options["port"] = global_options.get("port", 80)

    if 'login' not in options:
        assert global_options.get("login"), "login must be set either globally or locally"
        options["login"] = global_options.get("login")

    if 'password' not in options:
        assert global_options.get("password"), "password must be set either globally or locally"
        options["password"] = global_options.get("password")

    if 'model' not in options:
        assert global_options.get("model"), "model must be set either globally or locally"
        options["model"] = global_options.get("model")

    if 'fields' not in options:
        assert global_options.get("fields"), "model must be set either globally or locally"
        options["fields"] = global_options.get("fields")

    if 'domain' in global_options:
        # Check sporadically: https://github.com/sergiocorreia/panflute/issues/132
        global_domain = global_options.get("domain")
        global_domain_coerced = []
        for sub in global_domain:
            sub_coerced = []
            for leaf in sub:
                try:
                    sub_coerced.append(int(leaf))
                except:
                    try:
                        sub_coerced.append(float(leaf))
                    except:
                        sub_coerced.append(leaf)
            global_domain_coerced.append(sub_coerced)

        options["domain"] = options["domain"] + global_domain_coerced
        panflute.debug("pantable: combined domain '{}'.".format(options["domain"]))

    if 'pipe_tables' not in options:
        use_pipe_tables = global_options.get('pipe_tables', False)
    else:
        use_pipe_tables = options.get('pipe_tables', False)

    if 'grid_tables' not in options:
        use_grid_tables = global_options.get('grid_tables', False)
    else:
        use_grid_tables = options.get('grid_tables', False)

    try:
        if use_pipe_tables or use_grid_tables:
            # if both are specified, use grid_tables
            return odoo2table_markdown(options, data, use_grid_tables)
        else:
            return odoo2table_ast(options, data)

    # delete element if table is empty (by returning [])
    # element unchanged if include is invalid (by returning None)
    except FileNotFoundError:
        panflute.debug("pantable: include path not found. Codeblock shown as is.")
        return
    except EmptyTableError:
        panflute.debug("pantable: table is empty. Deleted.")
        # [] means delete the current element
        return []
    except ImportError:
        return


def main(doc=None):
    """
    Fenced code block with class table will be parsed using
    panflute.yaml_filter with the fuction convert2table above.
    """
    return panflute.run_filter(
        panflute.yaml_filter,
        tag='odootable',
        function=convert2table,
        strict_yaml=True,
        doc=doc
    )


if __name__ == '__main__':
    main()
