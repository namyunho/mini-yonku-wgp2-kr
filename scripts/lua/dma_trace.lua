-- dma_trace.lua : $420B(MDMAEN) 쓰기를 후킹해 모든 GP-DMA를 기록.
-- 목적: 텍스트/폰트 CHR가 어느 소스(ROM? WRAM?)에서 어느 VRAM 워드주소로 올라가는지 포착.
--   src 뱅크가 $7E/$7F(WRAM)  → 폰트가 런타임 디컴프됨(압축 확정 방향)
--   src 뱅크가 ROM($C0.. 등)  → 비압축 폰트가 ROM에 존재(정적 탐색 재조준)
-- 산출: tmp/trace/dma_log.txt
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local f = io.open(ROOT .. "dma_log.txt", "w")

local count, MAXLOG = 0, 40000
local STOP_FRAME = 1200   -- 약 20초까지 캡처

-- HiROM: PC = ((bank & 0x3F) << 16) | addr  (CLAUDE.md SSOT). WRAM 뱅크는 변환 무의미.
local function srcDesc(bank, addr)
  if bank == 0x7E or bank == 0x7F then
    return string.format("$%02X:%04X[WRAM]", bank, addr)
  end
  local pc = ((bank % 0x40) * 0x10000) + addr
  return string.format("$%02X:%04X(pc=0x%06X)", bank, addr, pc)
end

local function bbusName(d)
  if d == 0x18 or d == 0x19 then return "VRAM " end
  if d == 0x22 then return "CGRAM" end
  if d == 0x80 then return "WRAM " end
  if d == 0x04 then return "OAM  " end
  return string.format("$21%02X", d)
end

local function onDma(addr, value)
  local st = emu.getState()
  local frame = st["frameCount"]
  local vmadd = st["ppu.vramAddress"]      -- word 주소 (VRAM DMA 목적지)
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local dest = st[p .. "destAddress"]           -- B-bus reg 하위바이트
      local sb   = st[p .. "srcBank"]
      local sa   = st[p .. "srcAddress"]
      local size = st[p .. "transferSize"]           -- 0 == 65536
      local mode = st[p .. "transferMode"]
      local invert = st[p .. "invertDirection"]       -- true = B->A (PPU→CPU 읽기)
      local fixed  = st[p .. "fixedTransfer"]
      local tgt = bbusName(dest)
      local realsize = (size == 0) and 65536 or size
      local line = string.format(
        "f=%-4d ch%d %s src=%s size=%-5d mode=%d%s%s vmadd=$%04X",
        frame, ch, tgt, srcDesc(sb, sa), realsize, mode,
        fixed and " FIX" or "", invert and " B->A" or "", vmadd)
      f:write(line .. "\n")
      count = count + 1
    end
  end
  if count % 40 == 0 then f:flush() end
  if count > MAXLOG then f:flush(); f:close(); emu.stop(0) end
end

emu.addMemoryCallback(onDma, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)

-- 화면 진행: 인트로/타이틀을 지나 메뉴까지 Start 펄스 주입 (시그니처 방어적 시도)
local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end

local shotDone = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  -- 200~210, 400~410, 600~610 프레임에 Start 눌렀다 뗌
  if (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608) then
    pressStart(true)
  else
    pressStart(false)
  end
  if fr >= STOP_FRAME then
    if not shotDone then
      shotDone = true
      local ok, png = pcall(function() return emu.takeScreenshot() end)
      if ok and type(png) == "string" then
        local s = io.open(ROOT .. "screen_final.png", "wb")
        if s then s:write(png); s:close() end
      end
    end
    f:write(string.format("-- captured %d DMA rows, stopping at frame %d\n", count, fr))
    f:flush(); f:close()
    emu.stop(0)
  end
end

emu.addEventCallback(onFrame, emu.eventType.endFrame)
