"""Node contexts, parent links and the coverage rules will depend on."""

import ast

from app.engine.parser import PythonParser

SOURCE = (
    "import os\n"
    "\n"
    "class Signer:\n"
    "    def sign(self, key, payload):\n"
    "        for chunk in payload:\n"
    "            with open(chunk) as handle:\n"
    "                try:\n"
    "                    result = key.sign(handle)\n"
    "                except ValueError:\n"
    "                    result = None\n"
    "        return result\n"
    "\n"
    "async def run(items):\n"
    "    async for item in items:\n"
    "        await handle(item)\n"
    "    while items:\n"
    "        break\n"
    "    async with lock:\n"
    "        pass\n"
)


def parse(source: str = SOURCE, path: str = "src/signing.py"):
    return PythonParser().parse(source, path)


def test_a_deeply_nested_call_still_knows_its_function_and_class() -> None:
    parsed = parse()

    call = next(call for call in parsed.calls if call.function == "key.sign")
    assert call.enclosing_function == "Signer.sign"
    assert call.enclosing_class == "Signer"
    assert call.path == "src/signing.py"
    assert call.location.start_line == 8


def test_a_call_inside_an_async_function_records_it() -> None:
    parsed = parse()

    call = next(call for call in parsed.calls if call.function == "handle")
    assert call.enclosing_function == "run"
    assert call.enclosing_class is None


def test_every_node_has_a_recorded_context() -> None:
    parsed = parse()

    assert all(parsed.context_for(node) is not None for node in ast.walk(parsed.tree))


def test_a_context_links_back_to_its_parent() -> None:
    parsed = parse()

    call = next(call for call in parsed.calls if call.function == "key.sign")
    context = parsed.context_for(call.node)
    assert context.function == "Signer.sign"
    assert context.class_name == "Signer"
    assert context.module == "src.signing"
    assert isinstance(context.parent, ast.Assign)


def test_the_module_node_has_no_enclosing_definitions() -> None:
    parsed = parse()

    context = parsed.context_for(parsed.tree)
    assert context.parent is None
    assert context.function is None
    assert context.class_name is None


def test_control_flow_nodes_are_traversed() -> None:
    parsed = parse()
    kinds = {type(node) for node in ast.walk(parsed.tree)}

    for node_type in (
        ast.Module,
        ast.Import,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.Await,
        ast.Return,
        ast.Call,
        ast.Attribute,
        ast.Name,
        ast.Assign,
    ):
        assert node_type in kinds
        node = next(node for node in ast.walk(parsed.tree) if isinstance(node, node_type))
        assert parsed.context_for(node) is not None


def test_a_match_statement_is_traversed() -> None:
    parsed = parse(
        "def choose(value):\n"
        "    match value:\n"
        "        case {'algorithm': name}:\n"
        "            return use(name)\n"
        "        case _:\n"
        "            return None\n"
    )

    assert parsed.parsed
    call = parsed.calls[0]
    assert call.function == "use"
    assert call.enclosing_function == "choose"


def test_a_comprehension_call_records_its_enclosing_function() -> None:
    parsed = parse("def run(items):\n    return [sign(item) for item in items]\n")

    assert parsed.calls[0].enclosing_function == "run"


def test_a_lambda_body_belongs_to_the_enclosing_function() -> None:
    parsed = parse("def run():\n    return lambda value: sign(value)\n")

    assert parsed.calls[0].enclosing_function == "run"
