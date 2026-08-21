const fs = require('fs');

const code = fs.readFileSync('./goldeneaglehub.ultra.luau', 'utf8');
const strRegex = /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g;
let m;
let nonEmptyCount = 0;
while ((m = strRegex.exec(code)) !== null) {
  if (m[0] !== '""' && m[0] !== "''") {
    console.log('Non-empty string:', m[0]);
    nonEmptyCount++;
  }
}
console.log('Total non-empty plain string literals:', nonEmptyCount);
