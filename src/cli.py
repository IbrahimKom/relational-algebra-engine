"""Command-line entry point. See README.md for usage examples."""

import argparse
import sys

from .lexer import Lexer
from .parser import parse_program, parse_query
from .interpreter import build_environment, evaluate
from .printer import format_tree, format_relation
from .errors import RAError


def _tokenize(source):
    return Lexer(source).tokenize()


def run(argv=None):
    # the tree printer uses box-drawing characters; Windows consoles default
    # to a codepage that can't encode them, so force UTF-8 on stdout/stderr
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(prog="ra.py", description="Relational algebra engine")
    ap.add_argument("--relations", metavar="FILE",
                     help="a .ra file of relation definitions (and optionally a "
                          "trailing query) to load before running/printing a query")
    ap.add_argument("--tree", metavar="QUERY",
                     help="print the parse tree for QUERY without executing it")
    ap.add_argument("--query", metavar="QUERY",
                     help="execute QUERY against the relations loaded with --relations "
                          "and print the resulting table")
    args = ap.parse_args(argv)

    try:
        env = {}
        trailing_query_ast = None
        if args.relations:
            with open(args.relations, "r", encoding="utf-8") as f:
                source = f.read()
            reldefs, trailing_query_ast = parse_program(_tokenize(source))
            env = build_environment(reldefs)

        if args.tree is not None:
            tree_ast = parse_query(_tokenize(args.tree))
            print(format_tree(tree_ast))
            return 0

        query_ast = None
        if args.query is not None:
            query_ast = parse_query(_tokenize(args.query))
        elif trailing_query_ast is not None:
            query_ast = trailing_query_ast

        if query_ast is None:
            ap.error("nothing to do: pass --tree, --query, or a --relations "
                      "file that ends with a query")

        result = evaluate(query_ast, env)
        print(format_relation(result))
        return 0

    except RAError as e:
        print(e.format(), file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Error: file not found: {e.filename}", file=sys.stderr)
        return 1


def main():
    sys.exit(run())
