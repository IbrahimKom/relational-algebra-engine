from src.lexer import Lexer
from src.parser import parse_query, parse_program
from src.interpreter import build_environment, evaluate
from src.printer import format_tree


def tokenize(s):
    return Lexer(s).tokenize()


def tree(query):
    return format_tree(parse_query(tokenize(query)))


def parse(query):
    return parse_query(tokenize(query))


def load_env(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    reldefs, trailing_query = parse_program(tokenize(source))
    return build_environment(reldefs), trailing_query


def run(env, query):
    return evaluate(parse_query(tokenize(query)), env)


def rows(rel):
    return rel.tuples
