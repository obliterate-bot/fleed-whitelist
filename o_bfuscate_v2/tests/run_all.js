// tests/run_all.js
// Master test runner for O_bfuscate V2

console.log('\x1b[1m\x1b[35m====================================================\x1b[0m');
console.log('\x1b[1m\x1b[35m       O_bfuscate V2 - Test Suite Runner            \x1b[0m');
console.log('\x1b[1m\x1b[35m====================================================\x1b[0m\n');

try {
  require('./lexer.test.js');
  console.log('');
  require('./parser.test.js');
  console.log('');
  require('./transforms.test.js');
  console.log('');
  require('./e2e.test.js');
  console.log('\n\x1b[1m\x1b[32m====================================================\x1b[0m');
  console.log('\x1b[1m\x1b[32m  ALL TESTS PASSED! O_bfuscate V2 is fully verified.\x1b[0m');
  console.log('\x1b[1m\x1b[32m====================================================\x1b[0m');
} catch (err) {
  console.error('\n\x1b[31mTest failure:\x1b[0m', err);
  process.exit(1);
}
