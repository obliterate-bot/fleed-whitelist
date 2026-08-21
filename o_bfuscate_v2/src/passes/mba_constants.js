// src/passes/mba_constants.js
// Mixed Boolean-Arithmetic (MBA) & Constant Masking for Luau

const { NodeType, ASTNode, walk } = require('../core/ast');

class MBAPass {
  constructor(options = {}) {
    this.options = {
      intensity: options.mbaIntensity !== undefined ? options.mbaIntensity : 1, // 0 = off, 1 = moderate, 2 = deep
      maxTransformCount: options.maxMbaCount || 100,
      ...options
    };
    this.transformCount = 0;
  }

  apply(ast) {
    if (this.options.intensity <= 0) return ast;

    const numericNodes = [];

    walk(ast, {
      enter: (node, parent) => {
        if (node.type === NodeType.NumericLiteral) {
          // Avoid transforming step values, array indices inside decoder tables, or already huge numbers
          if (typeof node.value === 'number' && Number.isInteger(node.value) && Math.abs(node.value) < 1000000) {
            // Don't transform 0, 1, 2 if in tight index positions
            numericNodes.push({ node, parent });
          }
        }
      }
    });

    for (const { node, parent } of numericNodes) {
      if (this.transformCount >= this.options.maxTransformCount) break;

      const val = node.value;
      if (val >= 0 && val <= 65535) {
        const replacement = this.generateMBAExpression(val);
        if (replacement) {
          Object.assign(node, replacement);
          this.transformCount++;
        }
      }
    }

    return ast;
  }

  generateMBAExpression(target) {
    const strategy = Math.floor(Math.random() * 3);

    switch (strategy) {
      case 0: {
        // Linear MBA constant splitting: target = bit32.bxor(a, b) + diff
        const a = Math.floor(Math.random() * 0x3FFF) + 10;
        const b = Math.floor(Math.random() * 0x3FFF) + 10;
        const xorVal = a ^ b;
        const diff = target - xorVal;

        if (diff === 0) {
          return new ASTNode(NodeType.CallExpression, {
            base: new ASTNode(NodeType.MemberExpression, {
              base: new ASTNode(NodeType.Identifier, { name: 'bit32' }),
              identifier: new ASTNode(NodeType.Identifier, { name: 'bxor' }),
              indexer: '.'
            }),
            arguments: [
              new ASTNode(NodeType.NumericLiteral, { value: a, raw: `0x${a.toString(16)}` }),
              new ASTNode(NodeType.NumericLiteral, { value: b, raw: `0x${b.toString(16)}` })
            ]
          });
        }

        const op = diff > 0 ? '+' : '-';
        const absDiff = Math.abs(diff);

        return new ASTNode(NodeType.BinaryExpression, {
          operator: op,
          left: new ASTNode(NodeType.CallExpression, {
            base: new ASTNode(NodeType.MemberExpression, {
              base: new ASTNode(NodeType.Identifier, { name: 'bit32' }),
              identifier: new ASTNode(NodeType.Identifier, { name: 'bxor' }),
              indexer: '.'
            }),
            arguments: [
              new ASTNode(NodeType.NumericLiteral, { value: a, raw: `0x${a.toString(16)}` }),
              new ASTNode(NodeType.NumericLiteral, { value: b, raw: `0x${b.toString(16)}` })
            ]
          }),
          right: new ASTNode(NodeType.NumericLiteral, { value: absDiff, raw: `0x${absDiff.toString(16)}` })
        });
      }

      case 1: {
        // Algebraic MBA Identity:
        // target = (A * mult) - (A * mult - target)
        const mult = Math.floor(Math.random() * 8) + 2;
        const base = Math.floor(Math.random() * 50) + 5;
        const prod = base * mult;
        const offset = prod - target;

        const op = offset >= 0 ? '-' : '+';
        const absOffset = Math.abs(offset);

        return new ASTNode(NodeType.BinaryExpression, {
          operator: op,
          left: new ASTNode(NodeType.BinaryExpression, {
            operator: '*',
            left: new ASTNode(NodeType.NumericLiteral, { value: base, raw: String(base) }),
            right: new ASTNode(NodeType.NumericLiteral, { value: mult, raw: String(mult) })
          }),
          right: new ASTNode(NodeType.NumericLiteral, { value: absOffset, raw: `0x${absOffset.toString(16)}` })
        });
      }

      case 2:
      default: {
        // Hexadecimal polynomial split: target = (X + Y) ^ Z
        const z = Math.floor(Math.random() * 0xFF);
        const intermediate = target ^ z;
        const x = Math.floor(Math.random() * intermediate);
        const y = intermediate - x;

        return new ASTNode(NodeType.CallExpression, {
          base: new ASTNode(NodeType.MemberExpression, {
            base: new ASTNode(NodeType.Identifier, { name: 'bit32' }),
            identifier: new ASTNode(NodeType.Identifier, { name: 'bxor' }),
            indexer: '.'
          }),
          arguments: [
            new ASTNode(NodeType.BinaryExpression, {
              operator: '+',
              left: new ASTNode(NodeType.NumericLiteral, { value: x, raw: `0x${x.toString(16)}` }),
              right: new ASTNode(NodeType.NumericLiteral, { value: y, raw: `0x${y.toString(16)}` })
            }),
            new ASTNode(NodeType.NumericLiteral, { value: z, raw: `0x${z.toString(16)}` })
          ]
        });
      }
    }
  }
}

module.exports = {
  MBAPass
};
