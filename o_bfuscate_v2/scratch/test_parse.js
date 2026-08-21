const fs = require('fs');
const { obfuscate } = require('../src/engine');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const res = obfuscate(s, { preset: 'ultra-secure' });

const queries = ['Root', 'HumanoidObject', 'Direction', 'GiveConnection', 'FindFirstChildOfClass'];
for (const q of queries) {
  let count = 0;
  let idx = 0;
  while ((idx = res.code.indexOf(q, idx)) !== -1) {
    count++;
    idx += q.length;
  }
  console.log(`Count of "${q}" in output:`, count);
}
