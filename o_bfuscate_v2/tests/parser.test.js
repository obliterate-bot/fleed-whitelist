// tests/parser.test.js
const assert = require('assert');
const { Parser } = require('../src/core/parser');
const { NodeType } = require('../src/core/ast');
const { Generator } = require('../src/core/generator');

function test(name, fn) {
  try {
    fn();
    console.log(`  \x1b[32m✓\x1b[0m ${name}`);
  } catch (err) {
    console.error(`  \x1b[31m✗\x1b[0m ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

console.log('\x1b[1m\x1b[36mRunning Parser & Generator Tests...\x1b[0m');

test('Parses local statements and type annotations', () => {
  const code = 'local speed: number = 100\nlocal name: string = "Player1"';
  const parser = new Parser(code);
  const ast = parser.parse();

  assert.strictEqual(ast.body.length, 2);
  assert.strictEqual(ast.body[0].type, NodeType.LocalStatement);
  assert.strictEqual(ast.body[0].variables[0].name, 'speed');
  assert.strictEqual(ast.body[0].init[0].value, 100);
});

test('Parses compound assignments', () => {
  const code = 'x += 5; y *= 2';
  const parser = new Parser(code);
  const ast = parser.parse();

  assert.strictEqual(ast.body[0].type, NodeType.CompoundAssignmentStatement);
  assert.strictEqual(ast.body[0].operator, '+=');
  assert.strictEqual(ast.body[1].operator, '*=');
});

test('Parses Luau if-expressions (ternary)', () => {
  const code = 'local result = if hp > 0 then "alive" else "dead"';
  const parser = new Parser(code);
  const ast = parser.parse();

  assert.strictEqual(ast.body[0].init[0].type, NodeType.IfExpression);
});

test('Parses functions, while loops, and for loops', () => {
  const code = `
    local function compute(a, b)
      local total = 0
      for i = 1, 10 do
        total += i * a
      end
      return total + b
    end
  `;
  const parser = new Parser(code);
  const ast = parser.parse();

  assert.strictEqual(ast.body[0].type, NodeType.LocalFunctionDeclaration);
  assert.strictEqual(ast.body[0].parameters.length, 2);
});

test('Generates minified and watermarked code correctly', () => {
  const code = 'local x = 10; local y = 20; return x + y';
  const parser = new Parser(code);
  const ast = parser.parse();

  const generator = new Generator({
    watermark: 'protected by O_bfuscate v2, created by Undix',
    minify: true
  });
  const output = generator.generate(ast);

  assert(output.includes('protected by O_bfuscate v2, created by Undix'));
  assert(output.includes('local x=10 local y=20 return x+y'));
});
