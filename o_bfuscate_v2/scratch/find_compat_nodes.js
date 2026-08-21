const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ObfuscatorEngine } = require('../src/engine');
const { walk, NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

const engine = new ObfuscatorEngine({ preset: 'ultra-secure' });
engine.obfuscate(s);
