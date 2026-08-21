const fs = require('fs');
const { obfuscate } = require('../src/engine');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');

console.log('Obfuscating with ultra-secure preset...');
const res = obfuscate(s, { preset: 'ultra-secure' });

fs.writeFileSync('./goldeneaglehub.ultra.luau', res.code, 'utf8');
console.log('Saved goldeneaglehub.ultra.luau, size:', res.code.length);

// Scan for non-keyword identifiers of length >= 4
const LUA_KEYWORDS = new Set([
  'local', 'function', 'return', 'then', 'else', 'elseif', 'while', 'repeat', 'until', 'break', 'continue',
  'true', 'false', 'nil', 'self', 'pcall', 'type', 'math', 'string', 'table', 'bit32', 'bxor', 'buffer',
  'getfenv', 'native', 'optimize', 'protected', 'O_bfuscate', 'created', 'Undix', 'create', 'writeu8', 'readstring',
  'char', 'concat', 'error', 'pairs', 'ipairs', 'select', 'unpack', 'tostring', 'tonumber'
]);

const identRegex = /[a-zA-Z_][a-zA-Z0-9_]*/g;
const nonKeywords = new Map();
let m;
while ((m = identRegex.exec(res.code)) !== null) {
  const w = m[0];
  if (w.length >= 4 && !LUA_KEYWORDS.has(w) && !w.startsWith('_0x') && !w.startsWith('_а') && !w.startsWith('_е') && !w.startsWith('_о') && !w.startsWith('_р') && !w.startsWith('_с') && !w.startsWith('_у') && !w.startsWith('_х') && !w.startsWith('_і') && !w.startsWith('_ј') && !w.startsWith('_ѕ') && !w.startsWith('_А') && !w.startsWith('_В') && !w.startsWith('_Е') && !w.startsWith('_К') && !w.startsWith('_М') && !w.startsWith('_Н') && !w.startsWith('_О') && !w.startsWith('_Р') && !w.startsWith('_С') && !w.startsWith('_Т') && !w.startsWith('_Х')) {
    nonKeywords.set(w, (nonKeywords.get(w) || 0) + 1);
  }
}

console.log('Total non-keyword / non-mangled words found:', nonKeywords.size);
for (const [word, count] of nonKeywords.entries()) {
  console.log(`  "${word}": ${count} times`);
}
