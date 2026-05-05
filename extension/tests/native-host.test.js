/**
 * Unit tests for native-host.js
 *
 * Because native-host.js holds module-level state (port, pendingCalls,
 * nextId, _available), we use jest.isolateModules() to get a fresh copy
 * for each logical test group.
 */

describe('nativeCall', () => {
  let nativeCall;
  let mockPort;

  beforeEach(() => {
    jest.useFakeTimers();

    // Build a fresh mockPort
    mockPort = {
      postMessage: jest.fn(),
      disconnect: jest.fn(),
      onMessage: {
        _listeners: [],
        addListener(fn) { this._listeners.push(fn); },
        dispatch(msg) { this._listeners.forEach(fn => fn(msg)); },
      },
      onDisconnect: {
        _listeners: [],
        addListener(fn) { this._listeners.push(fn); },
        dispatch() { this._listeners.forEach(fn => fn()); },
      },
    };

    chrome.runtime.connectNative = jest.fn().mockReturnValue(mockPort);
    chrome.runtime.lastError = null;

    // Fresh module instance
    jest.resetModules();
    const mod = require('../src/lib/native-host.js');
    nativeCall = mod.nativeCall;
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.resetModules();
  });

  test('rejects when connectNative throws (host not available)', async () => {
    chrome.runtime.connectNative.mockImplementation(() => {
      throw new Error('Native host not found');
    });

    // Must reset modules again so native-host gets the throwing mock
    jest.resetModules();
    const mod = require('../src/lib/native-host.js');
    nativeCall = mod.nativeCall;

    await expect(nativeCall('getCourses', 'tok', 'https://canvas.vt.edu'))
      .rejects.toThrow('Native host is not available');
  });

  test('resolves when host responds with matching id', async () => {
    const promise = nativeCall('getCourses', 'tok', 'https://canvas.vt.edu', {});

    // Grab the id that was sent
    expect(mockPort.postMessage).toHaveBeenCalledTimes(1);
    const sentMsg = mockPort.postMessage.mock.calls[0][0];
    expect(sentMsg).toMatchObject({ method: 'getCourses', token: 'tok' });

    // Simulate host response
    mockPort.onMessage.dispatch({ id: sentMsg.id, ok: true, data: { courses: [] } });

    await expect(promise).resolves.toEqual({ courses: [] });
  });

  test('rejects when host responds with ok:false', async () => {
    const promise = nativeCall('getCourses', 'tok', 'https://canvas.vt.edu', {});
    const sentMsg = mockPort.postMessage.mock.calls[0][0];

    mockPort.onMessage.dispatch({ id: sentMsg.id, ok: false, error: 'Something went wrong' });

    await expect(promise).rejects.toThrow('Something went wrong');
  });

  test('rejects on timeout after RESPONSE_TIMEOUT_MS (10 s)', async () => {
    const promise = nativeCall('getAssignments', 'tok', 'https://canvas.vt.edu', {});

    // Do NOT dispatch a response — advance timers past the 10 s timeout
    jest.advanceTimersByTime(11_000);

    await expect(promise).rejects.toThrow(/timed out/i);
  });

  test('rejects if port disconnects mid-call', async () => {
    const promise = nativeCall('getCourses', 'tok', 'https://canvas.vt.edu', {});

    // Simulate the native host disconnecting before it replies
    mockPort.onDisconnect.dispatch();

    await expect(promise).rejects.toThrow('Native host disconnected');
  });

  test('ignores responses with unknown ids', async () => {
    const promise = nativeCall('getCourses', 'tok', 'https://canvas.vt.edu', {});
    const sentMsg = mockPort.postMessage.mock.calls[0][0];

    // Fire a response with a different id — should be ignored
    mockPort.onMessage.dispatch({ id: sentMsg.id + 99, ok: true, data: 'stray' });

    // Now resolve the real call
    mockPort.onMessage.dispatch({ id: sentMsg.id, ok: true, data: 'real' });

    await expect(promise).resolves.toBe('real');
  });
});

describe('isNativeHostAvailable', () => {
  let isNativeHostAvailable;
  let mockPort;

  beforeEach(() => {
    mockPort = {
      disconnect: jest.fn(),
      postMessage: jest.fn(),
      onMessage: { addListener: jest.fn() },
      onDisconnect: { addListener: jest.fn() },
    };
    chrome.runtime.connectNative = jest.fn().mockReturnValue(mockPort);
    chrome.runtime.lastError = null;

    jest.resetModules();
    const mod = require('../src/lib/native-host.js');
    isNativeHostAvailable = mod.isNativeHostAvailable;
  });

  afterEach(() => {
    jest.resetModules();
  });

  test('returns true when connectNative succeeds without lastError', () => {
    expect(isNativeHostAvailable()).toBe(true);
    expect(mockPort.disconnect).toHaveBeenCalled();
  });

  test('returns false when connectNative throws', () => {
    chrome.runtime.connectNative.mockImplementation(() => {
      throw new Error('Host not found');
    });

    jest.resetModules();
    const mod = require('../src/lib/native-host.js');
    isNativeHostAvailable = mod.isNativeHostAvailable;

    expect(isNativeHostAvailable()).toBe(false);
  });

  test('returns false when chrome.runtime.lastError is set', () => {
    chrome.runtime.lastError = { message: 'Specified native messaging host not found.' };

    jest.resetModules();
    const mod = require('../src/lib/native-host.js');
    isNativeHostAvailable = mod.isNativeHostAvailable;

    expect(isNativeHostAvailable()).toBe(false);
  });

  test('caches result after first call', () => {
    isNativeHostAvailable();
    isNativeHostAvailable();
    // connectNative was called only once (the nativeCall connect + the test check)
    // The second isNativeHostAvailable call should NOT call connectNative again
    const calls = chrome.runtime.connectNative.mock.calls.length;
    // First call to isNativeHostAvailable uses connectNative once; second uses cache
    expect(calls).toBe(1);
  });
});
