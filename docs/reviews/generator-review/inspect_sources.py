"""Read-only notebook/source inventory; writes only this review's evidence files."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'code' / 'synthetic-data'
OUT = Path(__file__).resolve().parent


def main():
    summaries = []
    for path in sorted(SOURCE.rglob('*.ipynb')):
        notebook = json.loads(path.read_text(encoding='utf-8-sig'))
        chunks = []
        imports = []
        syntax = []
        saved_errors = []
        for index, cell in enumerate(notebook.get('cells', [])):
            if cell.get('cell_type') != 'code':
                continue
            code = ''.join(cell.get('source', []))
            chunks.append(f'# NOTEBOOK CELL {index} (zero-based)\n{code}\n')
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(n.name for n in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or '<relative>')
            except SyntaxError as error:
                syntax.append({'cell': index, 'error': str(error)})
            for output in cell.get('outputs', []):
                if output.get('output_type') == 'error':
                    saved_errors.append({'cell': index, 'name': output.get('ename'), 'value': output.get('evalue')})
        stem = path.parent.name + '--' + path.stem
        extracted = OUT / (stem + '.source.txt')
        extracted.write_text('\n'.join(chunks), encoding='utf-8')
        summaries.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'code_cells': len(chunks), 'imports': sorted(set(imports)), 'syntax_errors': syntax,
                          'saved_errors': saved_errors, 'extracted': extracted.name})
    (OUT / 'source-inventory.json').write_text(json.dumps(summaries, indent=2), encoding='utf-8')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
