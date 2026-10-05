const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const zlib = require('node:zlib');
const crypto = require('node:crypto');

async function main() {
  const input = process.argv[2];
  const output = path.resolve(process.argv[3]);
  if (fs.statSync(input).size > 128 * 1024 * 1024) throw new Error('Capture size limit');
  fs.mkdirSync(output, { recursive: true });
  const html = fs.readFileSync(input, 'utf8');
  const comments = [...html.matchAll(/<!--([\s\S]*?)-->/g)];
  if (comments.length < 2 || !comments[0][1].startsWith('R0FL')) throw new Error('Capture magic mismatch');
  const raw = Buffer.concat([
    Buffer.from('\0\0\0\0R0FL'),
    zlib.inflateSync(Buffer.from(comments[0][1].slice(4), 'base64').subarray(8), { maxOutputLength: 128 * 1024 * 1024 }),
  ]);
  const toolsJs = zlib.inflateSync(Buffer.from(comments[1][1], 'base64').subarray(8), { maxOutputLength: 32 * 1024 * 1024 }).toString('utf8');
  const scriptStart = html.indexOf('<script>') + '<script>'.length;
  const scriptEnd = html.lastIndexOf('</script>');
  const viewerJs = html.slice(scriptStart, scriptEnd);
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  if (hash(viewerJs) !== 'e281dad0fefab7650435afb5986a0a86f0d5a1aee19d67317e3072b75de4dc27' || hash(toolsJs) !== '36a8c16e84cbc9a57381154227a74072ba471c752dd62167a3db4df918f85e46')
    throw new Error('Unsupported viewer format; retain dump and use native exports');
  const bootstrap = viewerJs.lastIndexOf('\nif (globalThis.g_cliMode)');
  if (bootstrap < 0) throw new Error('Embedded CLI initialization missing');
  const logs = [];
  const context = vm.createContext({
    g_cliMode: true,
    console: { log: (...xs) => logs.push(xs.join(' ')), warn: (...xs) => logs.push(xs.join(' ')), error: (...xs) => logs.push(xs.join(' ')) },
    TextDecoder, TextEncoder, WebAssembly,
    atob: s => Buffer.from(s, 'base64').toString('binary'),
    btoa: s => Buffer.from(s, 'binary').toString('base64'),
  });
  vm.runInContext('globalThis.self = globalThis;', context);
  vm.runInContext(viewerJs.slice(0, bootstrap), context, { timeout: 15000 });
  context.location.pathname = input;
  vm.runInContext('InitDataVars(); g_Loader.toolsData = {};', context);
  vm.runInContext(toolsJs, context, { timeout: 15000 });
  context.Tools = await context.ToolsModule();
  vm.runInContext("Tools.ccall('Init', 'number', [], []);", context, { timeout: 15000 });
  const exportOptions = JSON.parse(context.g_Loader.toolsData.exportResult);
  context.g_Loader.toolsData.exportOptions = exportOptions;
  context.g_Loader.toolsData.exportResult = null;
  context.rawLength = raw.length;
  const ptr = vm.runInContext('Tools._malloc(rawLength)', context, { timeout: 15000 });
  context.Tools.HEAPU8.set(raw, ptr);
  context.rawPtr = ptr;
  context.parseOptions = JSON.stringify({ fileName: path.basename(input), localId: 0, localGroupId: 0 });
  vm.runInContext("Tools.cwrap('ParseRaw', 'number', ['string', 'number', 'number'])(parseOptions, rawPtr, rawLength)", context, { timeout: 15000 });
  context.Tools._free(ptr);
  vm.runInContext('InitViewerVars(); InitPluginVars(); InitGroups(); InitFrameInfo(); PreprocessMinimal();', context, { timeout: 15000 });
  context.OpenNewExportTab = () => {};
  vm.runInContext('ExportSummaryJSON()', context, { timeout: 15000 });
  const stem = path.basename(input, '.html');
  fs.writeFileSync(path.join(output, stem + '_summary.json'), context.g_Loader.toolsData.exportResult);
  vm.runInContext('ExportCountersCSV()', context, { timeout: 15000 });
  fs.writeFileSync(path.join(output, stem + '_counters.csv'), context.g_Loader.toolsData.exportResult);
  fs.writeFileSync(path.join(output, stem + '.csv'), vm.runInContext('ExportMarkersCSV(true)', context, { timeout: 15000 }));
  fs.writeFileSync(path.join(output, 'viewer-data.json'), JSON.stringify({
    DumpHost: context.DumpHost, DumpUtcCaptureTime: context.DumpUtcCaptureTime,
    AggregateInfo: context.AggregateInfo, PlatformInfo: context.PlatformInfo,
    GeneralInfo: context.GeneralInfo, EnabledFastFlags: context.EnabledFastFlags,
    ThreadNames: context.ThreadNames, ThreadIds: context.ThreadIds, ThreadGpu: context.ThreadGpu,
    ThreadClobbered: context.ThreadClobbered, ThreadBufferSizes: context.ThreadBufferSizes,
    GroupInfo: context.GroupInfo, TimerInfo: context.TimerInfo,
    Frames: context.Frames.map(f => ({ ...f, lods: undefined })),
  }, (_key, value) => typeof value === 'bigint' ? value.toString() : value));
  const sha = data => crypto.createHash('sha256').update(data).digest('hex');
  fs.writeFileSync(path.join(output, 'export-provenance.json'), JSON.stringify({
    input, sha256: sha(Buffer.from(html)), bytes: Buffer.byteLength(html),
    method: 'Embedded viewer CLI mode; embedded WASM ParseRaw; native ExportSummaryJSON, ExportCountersCSV, ExportMarkersCSV',
    viewer_sha256: sha(viewerJs), tools_js_sha256: sha(toolsJs),
    initialization: 'InitViewerVars, InitPluginVars, InitGroups, InitFrameInfo, PreprocessMinimal',
    browser_or_computer_use: false, exports: exportOptions, logs,
  }, null, 2) + '\n');
  console.log('EXPORT|complete');
}

main().catch(e => { console.error(e); process.exitCode = 1; });
