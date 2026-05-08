# Clash Verge Script.js 分流配置

> 适用人群：不常驻 SII 的科研人员，或需要在校园网、复旦网络和漫游网络之间切换。
>
> 本文档对齐本机 Clash Verge profile 脚本结构。macOS 下常见路径为：
> `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/profiles/Script.js`。
>
> 下方脚本已去敏感化。所有 `<...>` 都是占位符，代理节点名、DNS 地址和校内直连 IP/CIDR 也已泛化；必须替换为你所在实验室 / 组织管理员分发的真实值，不要把真实 host、username、password、DNS、内网 / 校园网 IP 提交到仓库或聊天记录。

## 场景模式

`SITE_MODE` 控制本机所在网络：

| 值 | 场景 | `*.sii.edu.cn` 走向 |
| --- | --- | --- |
| `"sii"` | 创智 / SII 直连 | `DIRECT` |
| `"fudan"` | 复旦直连 | 走 `🧮 启智计算`代理组；复旦域名和指定校内地址直连 |
| `"roaming"` | 其它网络 | 走 `🧮 启智计算`代理组 |

脚本本身不强行设置 Clash Verge 监听端口。把 Clash Verge 的 mixed port 配成 `7897` 后，CLI 账号配置中填写 `http://127.0.0.1:7897` 或 `socks5://127.0.0.1:7897` 即可。

最小可用配置只需要两件事：

1. `*.sii.edu.cn` 在非创智直连场景走 `🧮 启智计算`代理组。
2. 其它公网流量继续走原订阅里的代理组或节点。

`LA` 链式出口只是本机 Script.js 里的可选特殊配置，用于把公网默认出口固定到一个额外 SOCKS5 节点。没有这类出口时保持 `USE_LA_EXIT = false`，并且不需要填写 `<la-proxy-...>` 占位符。

## 扩展脚本

```javascript
// Clash Verge 全局脚本。
// 场景："sii"=创智直连，"fudan"=复旦直连，"roaming"=其它网络。
var SITE_MODE = "fudan";

// 可选：LA 链式出口。这是本机示例里的特殊配置，不是 InspireSkill 必需项。
// 没有该出口时保持 false，公网流量会走原订阅里的 upstream proxies。
var USE_LA_EXIT = false;
var LA_NAME = "LA";
var LA_PROXY = {
  name: LA_NAME,
  type: "socks5",
  server: "<la-proxy-host>",
  port: 443,
  username: "<la-proxy-user>",
  password: "<la-proxy-password>",
  udp: true,
  "dialer-proxy": "upstream-proxies"
};

// 启智计算：非创智直连时访问 sii.edu.cn。
var QIZHI_GROUP_NAME = "🧮 启智计算";
var SII_PROXIES = [
  {
    name: "Sii-Proxy",
    type: "socks5",
    server: "<sii-proxy-primary-host>",
    port: 10808,
    username: "<sii-proxy-primary-user>",
    password: "<sii-proxy-primary-password>",
    tls: false,
    udp: true,
    "skip-cert-verify": true
  },
  {
    name: "Sii-Proxy-backup-1",
    type: "socks5",
    server: "<sii-proxy-secondary-host>",
    port: 10808,
    username: "<sii-proxy-secondary-user>",
    password: "<sii-proxy-secondary-password>",
    tls: false,
    udp: true,
    "skip-cert-verify": true
  },
  {
    name: "Sii-Proxy-backup-2",
    type: "socks5",
    server: "<sii-proxy-secondary-host>",
    port: 10809,
    username: "<sii-proxy-secondary-user>",
    password: "<sii-proxy-secondary-password>",
    tls: false,
    udp: true,
    "skip-cert-verify": true
  }
];
var QIZHI_GROUP = {
  name: QIZHI_GROUP_NAME,
  type: "select",
  proxies: ["Sii-Proxy", "Sii-Proxy-backup-1", "Sii-Proxy-backup-2", "DIRECT"]
};

// 规则改写时保留这些目标，其它统一走 Proxies。
var KEEP_TARGETS = { DIRECT: 1, REJECT: 1, "🧮 启智计算": 1 };

// 仅 fudan 场景使用。下面的 DNS 和 CIDR 是占位符，不要提交本机真实值。
var FUDAN_DNS = ["<fudan-dns-1>", "<fudan-dns-2>", "<fudan-dns-3>"];
var PUBLIC_DNS = ["<public-dns-1>", "<public-dns-2>", "<public-dns-3>"];
var FUDAN_DIRECT_CIDRS = ["<fudan-campus-service-cidr>"];

// 本脚本管理的代理名。
var MANAGED_PROXY_NAMES = {
  "LA": 1,
  "Sii-Proxy": 1,
  "Sii-Proxy-backup-1": 1,
  "Sii-Proxy-backup-2": 1
};

function ensureArray(v) { return Array.isArray(v) ? v : []; }
function ensureObject(v) { return v && typeof v === "object" && !Array.isArray(v) ? v : {}; }

function uniqueAppend(existing, additions) {
  var out = ensureArray(existing).slice();
  for (var i = 0; i < additions.length; i++) {
    if (out.indexOf(additions[i]) === -1) out.push(additions[i]);
  }
  return out;
}

// 已存在则先删除，保证规则顺序稳定。
function forceUnshift(rules, rule) {
  var idx = rules.indexOf(rule);
  if (idx !== -1) rules.splice(idx, 1);
  rules.unshift(rule);
}

function upsertProxy(proxies, newProxy) {
  var out = [];
  for (var i = 0; i < proxies.length; i++) {
    if (proxies[i] && proxies[i].name === newProxy.name) continue;
    out.push(proxies[i]);
  }
  out.push(newProxy);
  return out;
}

function upsertProxies(proxies, newProxies) {
  var out = proxies;
  for (var i = 0; i < newProxies.length; i++) {
    out = upsertProxy(out, newProxies[i]);
  }
  return out;
}

function removeProxyNames(proxies, names) {
  var out = [];
  for (var i = 0; i < proxies.length; i++) {
    var p = proxies[i];
    if (p && p.name && names[p.name]) continue;
    out.push(p);
  }
  return out;
}

function resetManagedProxies(config) {
  config.proxies = removeProxyNames(ensureArray(config.proxies), MANAGED_PROXY_NAMES);
}

// 注入可选 LA 链式出口。
function injectLA(config) {
  if (!USE_LA_EXIT) return;
  config.proxies = upsertProxy(ensureArray(config.proxies), LA_PROXY);
}

// sii.edu.cn 走启智计算组。
function injectQizhiProxy(config) {
  config.proxies = upsertProxies(ensureArray(config.proxies), SII_PROXIES);

  var rules = ensureArray(config.rules);
  forceUnshift(rules, "DOMAIN-SUFFIX,sii.edu.cn," + QIZHI_GROUP_NAME);
  config.rules = rules;
}

// 创智直连时，sii.edu.cn 直接走校园网。
function patchSiiCampus(config) {
  var rules = ensureArray(config.rules);
  forceUnshift(rules, "DOMAIN-SUFFIX,sii.edu.cn,DIRECT");
  config.rules = rules;
}

// 复旦直连时，复旦域名和 DNS 走校内。
function patchFudanCampus(config) {
  config.dns = ensureObject(config.dns);
  config.dns.enable = true;
  config.dns["direct-nameserver"] = uniqueAppend(
    FUDAN_DNS.slice(),
    PUBLIC_DNS.concat(ensureArray(config.dns["direct-nameserver"]))
  );
  config.dns["nameserver-policy"] = ensureObject(config.dns["nameserver-policy"]);
  config.dns["nameserver-policy"]["+.fudan.edu.cn"] = FUDAN_DNS.slice();

  var fudanRules = [
    "DOMAIN,icourse.fudan.edu.cn,DIRECT",
    "DOMAIN-SUFFIX,fudan.edu.cn,DIRECT"
  ];
  for (var c = 0; c < FUDAN_DIRECT_CIDRS.length; c++) {
    fudanRules.push("IP-CIDR," + FUDAN_DIRECT_CIDRS[c] + ",DIRECT,no-resolve");
  }
  var rules = ensureArray(config.rules);
  for (var i = fudanRules.length - 1; i >= 0; i--) {
    forceUnshift(rules, fudanRules[i]);
  }
  config.rules = rules;
}

// 重建组：默认复用订阅里的 upstream proxies；可选启用 LA 作为公网优先出口。
function rebuildProxyGroups(config) {
  var allProxies = ensureArray(config.proxies);
  var upstreamMembers = [];
  var seen = {};
  for (var i = 0; i < allProxies.length; i++) {
    var p = allProxies[i];
    if (!p || typeof p !== "object" || !p.name) continue;
    if (MANAGED_PROXY_NAMES[p.name]) continue;
    if (!seen[p.name]) { upstreamMembers.push(p.name); seen[p.name] = true; }
  }

  var groups = [];
  if (SITE_MODE !== "sii") groups.push(QIZHI_GROUP);
  if (upstreamMembers.length === 0) upstreamMembers = ["DIRECT"];
  var publicMembers = USE_LA_EXIT ? [LA_NAME, "upstream-proxies"] : ["upstream-proxies"];
  groups.push(
    { name: "Proxies", type: "select", proxies: publicMembers },
    { name: "upstream-proxies", type: "select", proxies: upstreamMembers }
  );
  config["proxy-groups"] = groups;

  var rules = ensureArray(config.rules);
  for (var k = 0; k < rules.length; k++) {
    var rule = rules[k];
    if (typeof rule !== "string") continue;
    var parts = rule.split(",");
    if (parts.length < 2) continue;
    var idx = parts.length - 1;
    if (parts[idx].trim() === "no-resolve") idx--;
    var target = parts[idx].trim();
    if (!KEEP_TARGETS[target]) {
      parts[idx] = "Proxies";
      rules[k] = parts.join(",");
    }
  }
  config.rules = rules;
}

// 国内和私网直连。
function patchCnDirect(config) {
  var cnRules = [
    "GEOSITE,private,DIRECT",
    "GEOSITE,cn,DIRECT",
    "GEOIP,private,DIRECT,no-resolve",
    "GEOIP,cn,DIRECT"
  ];
  var rules = ensureArray(config.rules);
  for (var i = cnRules.length - 1; i >= 0; i--) {
    forceUnshift(rules, cnRules[i]);
  }
  config.rules = rules;
}

function main(config, profileName) {
  resetManagedProxies(config);
  injectLA(config);
  patchCnDirect(config);
  if (SITE_MODE === "sii") {
    patchSiiCampus(config);
  } else {
    if (SITE_MODE === "fudan") patchFudanCampus(config);
    injectQizhiProxy(config);
  }
  rebuildProxyGroups(config);
  return config;
}
```

## 启用步骤

1. 打开 Clash Verge。
2. 进入订阅对应的全局扩展脚本编辑界面。
3. 粘贴脚本，替换所有 `<...>` 占位符。
4. 按当前网络设置 `SITE_MODE`。
5. 重新应用订阅或重载配置。
6. 在 Clash Verge 中确认 mixed port 监听 `127.0.0.1:7897`。

## 验证

先确认本机监听：

```bash
lsof -iTCP:7897 -sTCP:LISTEN
```

再验证公网和启智：

```bash
# 公网：经 Proxies 组；默认复用原订阅，USE_LA_EXIT=true 时优先走 LA
curl -sS -o /dev/null -w "public: %{http_code}\n" \
  -x socks5h://127.0.0.1:7897 https://www.google.com

# 启智：SITE_MODE=sii 时 DIRECT；其它模式走“🧮 启智计算”组
curl -sS -o /dev/null -w "sii:    %{http_code}\n" \
  -x socks5h://127.0.0.1:7897 https://qz.sii.edu.cn
```

如果启智返回 `000` 或连接超时：

1. 确认 `SITE_MODE` 是否符合当前网络。
2. 确认规则面板里有 `DOMAIN-SUFFIX,sii.edu.cn,DIRECT` 或 `DOMAIN-SUFFIX,sii.edu.cn,🧮 启智计算`。
3. 确认 `🧮 启智计算`组中的代理凭据仍有效。
4. 确认 Clash Verge mixed port 是 `7897`。
5. 如果没有本机特殊链式出口，确认 `USE_LA_EXIT = false`。

## 与 InspireSkill 的衔接

**CLI 不绑定 `7897`**。它只读取账号配置里的 `[proxy]`。如果 Clash Verge mixed port 是 `7897`，在 `inspire account add <name>` 中填写本机代理地址即可。

常用检查：

```bash
inspire config show --compact
inspire config check
inspire --debug resources list
```
