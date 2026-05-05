/**
 * Jest setup file — provides a global mock of the Chrome extension API.
 * Resets between tests via beforeEach hooks inside test files or
 * by calling jest.resetModules() as needed.
 */

const storageMap = new Map();
const sessionMap = new Map();

const mockPort = {
  postMessage: jest.fn(),
  onMessage: {
    _listeners: [],
    addListener(fn) { this._listeners.push(fn); },
    removeListener(fn) {
      this._listeners = this._listeners.filter(l => l !== fn);
    },
    dispatch(msg) { this._listeners.forEach(fn => fn(msg)); },
  },
  onDisconnect: {
    _listeners: [],
    addListener(fn) { this._listeners.push(fn); },
    removeListener(fn) {
      this._listeners = this._listeners.filter(l => l !== fn);
    },
    dispatch() { this._listeners.forEach(fn => fn()); },
  },
  disconnect: jest.fn(),
};

global.chrome = {
  runtime: {
    sendMessage: jest.fn(() => Promise.resolve()),
    connectNative: jest.fn(() => mockPort),
    lastError: null,
  },
  storage: {
    local: {
      get: jest.fn((keys) => {
        return Promise.resolve(
          Array.isArray(keys)
            ? keys.reduce((acc, k) => { acc[k] = storageMap.get(k); return acc; }, {})
            : { [keys]: storageMap.get(keys) }
        );
      }),
      set: jest.fn((items) => {
        Object.entries(items).forEach(([k, v]) => storageMap.set(k, v));
        return Promise.resolve();
      }),
    },
    session: {
      clear: jest.fn(() => {
        sessionMap.clear();
        return Promise.resolve();
      }),
    },
  },
  action: {
    setBadgeText: jest.fn(() => Promise.resolve()),
    setBadgeBackgroundColor: jest.fn(() => Promise.resolve()),
  },
  notifications: {
    create: jest.fn(() => Promise.resolve()),
  },
};

// Expose mockPort so tests can trigger onMessage / onDisconnect
global.__mockPort = mockPort;

// Helper to reset mocks between tests
global.__resetChromeMocks = function () {
  storageMap.clear();
  sessionMap.clear();
  mockPort.postMessage.mockReset();
  mockPort.disconnect.mockReset();
  mockPort.onMessage._listeners = [];
  mockPort.onDisconnect._listeners = [];
  chrome.runtime.sendMessage.mockReset();
  chrome.runtime.connectNative.mockReset();
  chrome.runtime.connectNative.mockReturnValue(mockPort);
  chrome.runtime.lastError = null;
  chrome.storage.local.get.mockReset();
  chrome.storage.local.set.mockReset();
  chrome.storage.session.clear.mockReset();
  chrome.action.setBadgeText.mockReset();
  chrome.action.setBadgeBackgroundColor.mockReset();
  chrome.notifications.create.mockReset();
};
