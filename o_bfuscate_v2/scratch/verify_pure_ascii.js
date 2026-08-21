const fs = require('fs');
const { obfuscate } = require('../src/engine');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');

console.log('Testing ultra-secure preset for non-ASCII characters...');
const resUltra = obfuscate(s, { preset: 'ultra-secure' });
fs.writeFileSync('./goldeneaglehub.ultra.luau', resUltra.code, 'utf8');

let nonAsciiCount = 0;
for (let i = 0; i < resUltra.code.length; i++) {
  const code = resUltra.code.charCodeAt(i);
  if (code > 127) {
    console.log(`Non-ASCII character found at index ${i}: char='${resUltra.code[i]}', code=U+${code.toString(16).padStart(4, '0')}`);
    nonAsciiCount++;
    if (nonAsciiCount >= 10) break;
  }
}

console.log(`Total non-ASCII characters in ultra-secure output: ${nonAsciiCount}`);

console.log('Testing max-performance preset for non-ASCII characters...');
const resPerf = obfuscate(s, { preset: 'max-performance' });
fs.writeFileSync('./goldeneaglehub.obf.luau', resPerf.code, 'utf8');

let nonAsciiPerf = 0;
for (let i = 0; i < resPerf.code.length; i++) {
  const code = resPerf.code.charCodeAt(i);
  if (code > 127) {
    nonAsciiPerf++;
  }
}
console.log(`Total non-ASCII characters in max-performance output: ${nonAsciiPerf}`);
