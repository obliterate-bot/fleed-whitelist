const { Parser } = require('../src/core/parser');
const { IdentifierMangler } = require('../src/passes/mangler');
const { Generator } = require('../src/core/generator');

const code = `
function State.AutoBody.GetCurrentHand(Character, HumanoidObject, Root)
  local Animator = HumanoidObject and HumanoidObject:FindFirstChildOfClass('Animator')
  return Character, HumanoidObject, Root
end
`;

const p = new Parser(code);
const ast = p.parse();

const mangler = new IdentifierMangler({ manglerMode: 'confusables' });
mangler.apply(ast);

const gen = new Generator({ minify: true });
console.log(gen.generate(ast));
