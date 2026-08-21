const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { MemberIndirectionPass } = require('../src/passes/member_indirection');
const { AntiTamperPass } = require('../src/passes/anti_tamper');
const { ControlFlowFlatteningPass } = require('../src/passes/control_flow');
const { OpaquePredicatesPass } = require('../src/passes/opaque_predicates');
const { MBAPass } = require('../src/passes/mba_constants');
const { StringCryptoPass } = require('../src/passes/string_crypto');
const { IdentifierMangler } = require('../src/passes/mangler');
const { Generator } = require('../src/core/generator');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

new MemberIndirectionPass().apply(ast);
new AntiTamperPass().apply(ast);
new ControlFlowFlatteningPass({ cffIntensity: 2 }).apply(ast);
new OpaquePredicatesPass({ opaqueIntensity: 2 }).apply(ast);
new MBAPass({ mbaIntensity: 2 }).apply(ast);
new StringCryptoPass().apply(ast);
new IdentifierMangler({ manglerMode: 'confusables' }).apply(ast);

const gen = new Generator({ minify: true });
const out = gen.generate(ast);

console.log('out includes Compat:', out.includes('Compat'));
if (out.includes('Compat')) {
  let idx = 0;
  while ((idx = out.indexOf('Compat', idx)) !== -1) {
    console.log(out.substring(idx-30, idx+50));
    idx += 6;
  }
}
