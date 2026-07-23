-- trace_text.lua : 대사 파서 $C1:9554 진입을 후킹해 게임이 실제로 읽는
--   모든 대사 글리프 주소(DBR:Y)와 호출처(JSL 복귀주소)를 연속 수집.
--   목적: 정적 열거(673)가 놓친 어드벤처/스토리 대사 블록의 뱅크·범위를 실측으로 확정.
--   사용법: 원본 ROM으로 실행 → 어드벤처(맵 이동·대화)·레이스·메뉴를 두루 플레이.
--   산출(약 1초마다 갱신): tmp/trace/text_addrs.txt  (뱅크별 스팬 + 호출처 + 전체 주소)
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"

local seen = {}            -- key(bank*0x10000+addr) -> true
local nseen = 0
local calls = 0
local bankmin = {}         -- bank -> min addr
local bankmax = {}         -- bank -> max addr
local bankcnt = {}         -- bank -> distinct count
local sites = {}           -- return addr -> count

local function onExec()
  calls = calls + 1
  local st = emu.getState()
  local dbr = st["cpu.dbr"]
  local y = st["cpu.y"]
  if dbr ~= nil and y ~= nil then
    local key = dbr * 0x10000 + y
    if not seen[key] then
      seen[key] = true; nseen = nseen + 1
      if bankmin[dbr] == nil or y < bankmin[dbr] then bankmin[dbr] = y end
      if bankmax[dbr] == nil or y > bankmax[dbr] then bankmax[dbr] = y end
      bankcnt[dbr] = (bankcnt[dbr] or 0) + 1
    end
  end
  -- 호출처(JSL 복귀주소 = S+1..S+3)
  local s = st["cpu.sp"]
  if s ~= nil then
    local r1 = emu.read(s + 1, emu.memType.snesMemory)
    local r2 = emu.read(s + 2, emu.memType.snesMemory)
    local r3 = emu.read(s + 3, emu.memType.snesMemory)
    local ret = (r3 << 16) | (r2 << 8) | r1
    sites[ret] = (sites[ret] or 0) + 1
  end
end

emu.addMemoryCallback(onExec, emu.callbackType.exec, 0xC19554, 0xC19554,
  emu.cpuType.snes, emu.memType.snesMemory)

local function dump()
  local f = io.open(ROOT .. "text_addrs.txt", "w")
  if not f then return end
  f:write(string.format("# frame=%d parser_calls=%d distinct_addrs=%d\n\n",
    emu.getState()["frameCount"], calls, nseen))
  -- 뱅크별 스팬 (읽힌 대사 뱅크)
  local banks = {}
  for b, _ in pairs(bankcnt) do banks[#banks + 1] = b end
  table.sort(banks)
  f:write("## 뱅크별 대사 스팬 (게임이 읽은 텍스트) ##\n")
  for _, b in ipairs(banks) do
    f:write(string.format("BANK $%02X : n=%-5d  $%04X..$%04X\n", b, bankcnt[b], bankmin[b], bankmax[b]))
  end
  -- 호출처 (빈도순)
  f:write("\n## 파서 호출처 (JSL 복귀주소 x횟수) ##\n")
  local ss = {}
  for k, v in pairs(sites) do ss[#ss + 1] = { k, v } end
  table.sort(ss, function(a, b) return a[2] > b[2] end)
  for i = 1, math.min(#ss, 20) do
    f:write(string.format("site $%06X  x%d\n", ss[i][1], ss[i][2]))
  end
  -- 전체 주소 목록 (뱅크:주소)
  f:write("\n## 전체 읽힌 주소 ##\n")
  local addrs = {}
  for k, _ in pairs(seen) do addrs[#addrs + 1] = k end
  table.sort(addrs)
  for _, k in ipairs(addrs) do
    f:write(string.format("%02X:%04X\n", k // 0x10000, k % 0x10000))
  end
  f:close()
end

-- 약 1초(60프레임)마다 파일 갱신. 자동입력 없음(사용자가 직접 플레이).
local fc = 0
local function onFrame()
  fc = fc + 1
  if fc % 60 == 0 then pcall(dump) end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
