// tests/lexer.test.js
const assert = require('assert');
const { Lexer } = require('../src/core/lexer');
const { TokenType } = require('../src/core/tokens');

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

console.log('\x1b[1m\x1b[36mRunning Lexer Tests...\x1b[0m');

test('Tokenizes basic literals and identifiers', () => {
  const code = 'local x = 123.45 + "hello"';
  const lexer = new Lexer(code);
  const tokens = lexer.tokenize();

  assert.strictEqual(tokens[0].type, TokenType.Keyword);
  assert.strictEqual(tokens[0].value, 'local');
  assert.strictEqual(tokens[1].type, TokenType.Identifier);
  assert.strictEqual(tokens[1].value, 'x');
  assert.strictEqual(tokens[2].type, TokenType.Operator);
  assert.strictEqual(tokens[2].value, '=');
  assert.strictEqual(tokens[3].type, TokenType.Number);
  assert.strictEqual(tokens[3].value, 123.45);
  assert.strictEqual(tokens[4].type, TokenType.Operator);
  assert.strictEqual(tokens[4].value, '+');
  assert.strictEqual(tokens[5].type, TokenType.String);
  assert.strictEqual(tokens[5].value, 'hello');
});

test('Tokenizes Luau compound operators and continue', () => {
  const code = 'x += 10; y -= 5; z *= 2; continue';
  const lexer = new Lexer(code);
  const tokens = lexer.tokenize();

  assert.strictEqual(tokens[1].value, '+=');
  assert.strictEqual(tokens[5].value, '-=');
  assert.strictEqual(tokens[9].value, '*=');
  assert.strictEqual(tokens[12].type, TokenType.Keyword);
  assert.strictEqual(tokens[12].value, 'continue');
});

test('Tokenizes Hex numbers and Binary numbers', () => {
  const code = 'local hex = 0x5a3f; local bin = 0b1011';
  const lexer = new Lexer(code);
  const tokens = lexer.tokenize();

  assert.strictEqual(tokens[3].value, 0x5a3f);
  assert.strictEqual(tokens[8].value, 11);
});

test('Tokenizes Luau string interpolation', () => {
  const code = 'local s = `Value is {x + 1}!`';
  const lexer = new Lexer(code);
  const tokens = lexer.tokenize();

  assert.strictEqual(tokens[3].type, TokenType.InterpolatedString);
  assert.strictEqual(tokens[3].value.length, 3);
});

test('Tokenizes multi-line comments and directives', () => {
  const code = '--!native\n--!optimize 2\nlocal a = 1';
  const lexer = new Lexer(code);
  const tokens = lexer.tokenize();

  assert.deepStrictEqual(lexer.directives, ['!native', '!optimize 2']);
  assert.strictEqual(tokens[0].value, 'local');
});
