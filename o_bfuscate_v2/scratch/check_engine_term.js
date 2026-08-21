const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ObfuscatorEngine } = require('../src/engine');
const { walk, NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const engine = new ObfuscatorEngine({ preset: 'ultra-secure' });
const res = engine.obfuscate(s);

if (res.code.includes('TerminalStroke')) {
  console.log('Found TerminalStroke in engine output!');
  const idx = res.code.indexOf('TerminalStroke');
  console.log('Snippet:', res.code.substring(idx - 40, idx + 60));
} else {
  console.log('TerminalStroke is NOT in engine output!');
}
