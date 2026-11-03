/* ============================================================
   接口层。统一携带令牌、统一抛出可读错误。
   ============================================================ */
const API = (() => {
  const KEY = 'kr_token';
  let token = localStorage.getItem(KEY) || '';

  function set(t) { token = t; localStorage.setItem(KEY, t); }
  function clear() { token = ''; localStorage.removeItem(KEY); }
  function has() { return !!token; }

  async function req(path, opt = {}) {
    const headers = {};
    if (token) headers['Authorization'] = 'Bearer ' + token;
    let body = opt.body;
    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    const res = await fetch(path, { method: opt.method || 'GET', headers, body });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && data.detail) || ('请求失败 ' + res.status);
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  const get  = (p)        => req(p);
  const post = (p, b)     => req(p, { method: 'POST', body: b });
  const put  = (p, b)     => req(p, { method: 'PUT',  body: b });
  const patch= (p, b)     => req(p, { method: 'PATCH',body: b });
  const del  = (p)        => req(p, { method: 'DELETE' });

  async function upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    return req('/api/upload', { method: 'POST', body: fd });
  }

  /* 带额外表单字段的上传：教材上传要同时带书名、学科这些元信息 */
  async function uploadWith(path, file, fields) {
    const fd = new FormData();
    fd.append('file', file);
    Object.keys(fields || {}).forEach(k => fd.append(k, fields[k] == null ? '' : fields[k]));
    return req(path, { method: 'POST', body: fd });
  }

  // pdf.js 自己发请求，拿不到 req() 里加的请求头，所以把令牌单独暴露出去
  function getToken() { return token; }

  return { set, clear, has, get, post, put, patch, del, upload, uploadWith, req, getToken };
})();
