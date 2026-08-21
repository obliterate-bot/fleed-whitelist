const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ObfuscatorEngine } = require('../src/engine');
const { walk, NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const engine = new ObfuscatorEngine({ preset: 'ultra-secure' });
const res = engine.obfuscate(s);

if (res.code.includes('SetTerminalStatus')) {
  console.log('Found SetTerminalStatus in engine output!');
  let idx = 0;
  while ((idx = res.code.indexOf('SetTerminalStatus', idx)) !== -1) {
    console.log(res.code.substring(idx-30, idx+50));
    idx += 17;
  }
} else {
  console.log('SetTerminalStatus NOT found in engine output!');
}
