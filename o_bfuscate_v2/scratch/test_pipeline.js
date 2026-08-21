const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { MemberIndirectionPass } = require('../src/passes/member_indirection');
const { ControlFlowFlatteningPass } = require('../src/passes/control_flow');
const { OpaquePredicatesPass } = require('../src/passes/opaque_predicates');
const { MBAPass } = require('../src/passes/mba_constants');
const { StringCryptoPass } = require('../src/passes/string_crypto');
const { IdentifierMangler } = require('../src/passes/mangler');
const { Generator } = require('../src/core/generator');
const { walk, NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

console.log('1. Parsed AST');

const memberPass = new MemberIndirectionPass();
memberPass.apply(ast);
console.log('2. Applied MemberIndirectionPass');

const cffPass = new ControlFlowFlatteningPass({ cffIntensity: 2 });
cffPass.apply(ast);
console.log('3. Applied ControlFlowFlatteningPass');

const opaquePass = new OpaquePredicatesPass({ opaqueIntensity: 2 });
opaquePass.apply(ast);
console.log('4. Applied OpaquePredicatesPass');

const mbaPass = new MBAPass({ mbaIntensity: 2 });
mbaPass.apply(ast);
console.log('5. Applied MBAPass');

const cryptoPass = new StringCryptoPass();
cryptoPass.apply(ast);
console.log('6. Applied StringCryptoPass');

const mangler = new IdentifierMangler({ manglerMode: 'confusables' });
mangler.apply(ast);
console.log('7. Applied IdentifierMangler');

let unmangledFakeModal = 0;
walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.Identifier && node.name === 'FakeModal') {
      if (!node.mangledName) {
        unmangledFakeModal++;
        console.log('Unmangled FakeModal node parent:', node);
      }
    }
  }
});
console.log('Total unmangled FakeModal nodes:', unmangledFakeModal);
