// tests/transforms.test.js
const assert = require('assert');
const { Parser } = require('../src/core/parser');
const { Generator } = require('../src/core/generator');
const { StringCryptoPass } = require('../src/passes/string_crypto');
const { IdentifierMangler } = require('../src/passes/mangler');
const { MBAPass } = require('../src/passes/mba_constants');
const { ControlFlowFlatteningPass } = require('../src/passes/control_flow');
const { MemberIndirectionPass } = require('../src/passes/member_indirection');

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

console.log('\x1b[1m\x1b[36mRunning Transformation Pass Tests...\x1b[0m');

test('String Crypto Pass encodes strings and generates buffer decoder', () => {
  const code = 'local greeting = "Hello World!"; print(greeting)';
  const parser = new Parser(code);
  const ast = parser.parse();

  const pass = new StringCryptoPass();
  pass.apply(ast);

  const gen = new Generator();
  const output = gen.generate(ast);

  // The raw string "Hello World!" should no longer appear in plain text
  assert(!output.includes('"Hello World!"'));
  assert(output.includes('_S'));
});

test('Identifier Mangler scrambles local names', () => {
  const code = 'local secretValue = 42; local other = secretValue + 10; return other';
  const parser = new Parser(code);
  const ast = parser.parse();

  const pass = new IdentifierMangler({ manglerMode: 'hex_hash' });
  pass.apply(ast);

  const gen = new Generator();
  const output = gen.generate(ast);

  assert(!output.includes('secretValue'));
  assert(!output.includes('other'));
  assert(output.includes('_0x'));
});

test('MBA Pass replaces numeric constants with bitwise expressions', () => {
  const code = 'local damage = 1500';
  const parser = new Parser(code);
  const ast = parser.parse();

  const pass = new MBAPass({ intensity: 1 });
  pass.apply(ast);

  const gen = new Generator();
  const output = gen.generate(ast);

  assert(output.includes('bit32.bxor') || output.includes('0x') || output.includes('*'));
});

test('Control Flow Flattening turns function body into state dispatcher', () => {
  const code = `
    local function testFlow()
      local a = 1
      local b = 2
      local c = a + b
      return c
    end
  `;
  const parser = new Parser(code);
  const ast = parser.parse();

  const pass = new ControlFlowFlatteningPass({ intensity: 1 });
  pass.apply(ast);

  const gen = new Generator();
  const output = gen.generate(ast);

  assert(output.includes('while') && output.includes('_cff_st_'));
});

test('Member Indirection localizes global fastcalls', () => {
  const code = 'local val = math.sin(1.5) + math.cos(0.5)';
  const parser = new Parser(code);
  const ast = parser.parse();

  const pass = new MemberIndirectionPass({ localizeGlobals: true, indirectMembers: true });
  pass.apply(ast);

  const gen = new Generator();
  const output = gen.generate(ast);

  assert(output.includes('_g_math_sin') || output.includes('_g_math_cos'));
});
