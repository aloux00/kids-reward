/**
 * 用自托管的 pdf.js 逐本打开教材，检查文件是否完好，并把总页数记下来。
 *
 * 为什么要这一步：
 * 1) 验证 —— 449MB 的东西从 6 个镜像拼下来，必须确认每一本都能真打开，
 *    而不是"文件大小对了就算成功"。
 * 2) 页数 —— 家长布置「读第 1-6 页」时要知道这本书到底多少页；
 *    等孩子第一次翻开才回写太被动了。
 *
 *   node tools/probe_pages.mjs
 * 产出：data/textbook-pages.json  { "<目录里的路径>": 页数 }
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const VENDOR = path.join(ROOT, 'static', 'vendor', 'pdfjs');
const CATALOG = path.join(ROOT, 'data', 'textbook-catalog.json');
const BOOKS = path.join(ROOT, 'data', 'textbooks');
const OUT = path.join(ROOT, 'data', 'textbook-pages.json');

const pdfjs = await import(pathToFileURL(path.join(VENDOR, 'pdf.min.mjs')).href);
pdfjs.GlobalWorkerOptions.workerSrc = pathToFileURL(path.join(VENDOR, 'pdf.worker.min.mjs')).href;

// 必须和 app/services/textbook.py 的 file_name_for 保持一致
const fileNameFor = (p) => crypto.createHash('sha1').update(p, 'utf8').digest('hex').slice(0, 16) + '.pdf';

const catalog = JSON.parse(fs.readFileSync(CATALOG, 'utf8'));
const pages = {};
let ok = 0, missing = 0, broken = 0;

for (const b of catalog.books) {
  const file = path.join(BOOKS, fileNameFor(b.path));
  if (!fs.existsSync(file)) { missing++; continue; }
  try {
    const data = new Uint8Array(fs.readFileSync(file));
    const doc = await pdfjs.getDocument({ data, useWorkerFetch: false, isEvalSupported: false }).promise;
    pages[b.path] = doc.numPages;
    await doc.destroy();
    ok++;
    console.log(`  ✅ ${String(doc.numPages).padStart(4)} 页  ${b.title}`);
  } catch (e) {
    broken++;
    console.log(`  ❌ 打不开 ${b.title}: ${String(e.message || e).slice(0, 80)}`);
  }
}

fs.writeFileSync(OUT, JSON.stringify(pages, null, 0), 'utf8');
console.log(`\n可打开 ${ok} 本，未下载 ${missing} 本，损坏 ${broken} 本`);
console.log(`页数已写入 ${OUT}`);
if (broken) process.exit(1);
