module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['./tests/setup.js'],
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  coverageThreshold: {
    global: {
      lines: 70,
      functions: 70,
      branches: 70,
    },
  },
  collectCoverageFrom: [
    'src/lib/canvas-client.js',
    'src/lib/native-host.js',
  ],
  testMatch: ['**/tests/**/*.test.js'],
};
