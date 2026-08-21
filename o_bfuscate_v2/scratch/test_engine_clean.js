const fs = require('fs');
const { ObfuscatorEngine } = require('../src/engine');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');

console.log('Obfuscating with ultra-secure preset...');
const engine = new ObfuscatorEngine({ preset: 'ultra-secure' });
const res = engine.obfuscate(s);

fs.writeFileSync('./goldeneaglehub.ultra.luau', res.code, 'utf8');
console.log('Saved goldeneaglehub.ultra.luau, size:', res.code.length);

const LUA_KEYWORDS = new Set([
  'local', 'function', 'return', 'then', 'else', 'elseif', 'while', 'repeat', 'until', 'break', 'continue',
  'true', 'false', 'nil', 'self', 'pcall', 'type', 'math', 'string', 'table', 'bit32', 'bxor', 'buffer',
  'getfenv', 'native', 'optimize', 'protected', 'O_bfuscate', 'created', 'Undix', 'create', 'writeu8', 'readstring',
  'char', 'concat', 'error', 'pairs', 'ipairs', 'select', 'unpack', 'tostring', 'tonumber', 'setmetatable',
  'for', 'in', 'do', 'end', 'and', 'or', 'not'
]);

// Extract all identifier tokens from code
const identRegex = /[a-zA-Z_][a-zA-Z0-9_]*/g;
const nonKeywords = new Map();
let m;
while ((m = identRegex.exec(res.code)) !== null) {
  const w = m[0];
  // Check if it's not a standard keyword and not starting with a mangled prefix (_0x or unicode confusables)
  if (!LUA_KEYWORDS.has(w) && !w.startsWith('_') && w.length >= 3) {
    nonKeywords.set(w, (nonKeywords.get(w) || 0) + 1);
  }
}

console.log('Total un-mangled plain words found:', nonKeywords.size);
for (const [word, count] of nonKeywords.entries()) {
  console.log(`  "${word}": ${count} times`);
}
