-- probe_box.lua : 패시브 렌더 로거 (세이브스테이트 불필요).
--   렌더러 $C0:6844 후킹 → 글리프별 라인 base($22)·펜 X($24)·글리프 인덱스($26) 기록.
--   ($C0:6827 에서 TCD로 DP를 스택프레임에 맞춘 뒤라 D+0x22/24/26 = 인자 슬롯)
--   최근 N개만 링버퍼로 유지하고 주기적으로 파일 플러시.
--   사용법: 이 스크립트로 실행 → 클립되는 상자를 화면에 띄운 직후 Mesen 종료.
--            → tmp/trace/box_render.txt 의 마지막 렌더 묶음이 그 상자.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local CAP = 2500

local buf = {}      -- 링버퍼
local head = 0
local total = 0

local function onGlyph()
  local st = emu.getState()
  local d = st["cpu.d"]
  local base = emu.read(d + 0x22, emu.memType.snesWorkRam) + emu.read(d + 0x23, emu.memType.snesWorkRam) * 256
  local penx = emu.read(d + 0x24, emu.memType.snesWorkRam) + emu.read(d + 0x25, emu.memType.snesWorkRam) * 256
  local gidx = emu.read(d + 0x26, emu.memType.snesWorkRam) + emu.read(d + 0x27, emu.memType.snesWorkRam) * 256
  head = (head % CAP) + 1
  buf[head] = string.format("f=%d base=$%04X penX=%d glyph=$%03X", st["frameCount"], base, penx, gidx)
  total = total + 1
end
emu.addMemoryCallback(onGlyph, emu.callbackType.exec, 0xC06844, 0xC06844,
  emu.cpuType.snes, emu.memType.snesMemory)

local function flush()
  local f = io.open(ROOT .. "box_render.txt", "w")
  if not f then return end
  f:write(string.format("# total glyph-renders=%d (링버퍼 최근 %d 유지)\n", total, CAP))
  -- head 다음부터 순서대로 (오래된 것 → 최신)
  for k = 1, CAP do
    local idx = (head + k - 1) % CAP + 1
    if buf[idx] then f:write(buf[idx] .. "\n") end
  end
  f:close()
end

local function shot()
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local s = io.open(ROOT .. "box_state.png", "wb"); if s then s:write(png); s:close() end
  end
end

local fc = 0
emu.addEventCallback(function()
  fc = fc + 1
  if fc % 60 == 0 then pcall(flush); pcall(shot) end
end, emu.eventType.endFrame)
