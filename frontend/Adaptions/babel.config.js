module.exports = {
  presets: [
    '@babel/preset-env',
    '@babel/preset-react'
  ],
  plugins: [
    'babel-plugin-styled-components',
    '@babel/plugin-transform-runtime',
    '@babel/plugin-proposal-class-properties',
    '@babel/plugin-proposal-private-methods'
  ],
  env: {
    development: {
      plugins: [
        'react-refresh/babel'
      ]
    },
    production: {
      plugins: [
        'babel-plugin-transform-react-remove-prop-types',
        ['babel-plugin-transform-remove-console', { exclude: ['error', 'warn'] }]
      ]
    },
    test: {
      presets: [
        ['@babel/preset-env', { targets: { node: 'current' } }]
      ]
    }
  }
};
