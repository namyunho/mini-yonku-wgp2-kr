-- dump_mem.lua : 대사창(「栄光のゴール…」)이 뜬 시점에 WRAM/VRAM/CGRAM 전체를 파일로 덤프.
-- 오프라인에서 render-tiles로 폰트 시트·텍스트 합성 버퍼를 찾기 위함.
-- 산출: tmp/trace/{wram.bin(128K), vram.bin(64K), cgram.bin(512), dump_meta.txt}
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local DUMP_FRAME = 1200

local function dumpMem(memType, size, path)
  local buf = {}
  local chunk = {}
  for i = 0, size - 1 do
    chunk[#chunk + 1] = string.char(emu.read(i, memType))
    if #chunk == 4096 then
      buf[#buf + 1] = table.concat(chunk)
      chunk = {}
    end
  end
  if #chunk > 0 then buf[#buf + 1] = table.concat(chunk) end
  local fh = io.open(path, "wb")
  fh:write(table.concat(buf))
  fh:close()
end

local done = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  -- 타이틀→모드선택→레이스로 진행 (dma_trace와 동일 펄스)
  local on = (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608)
  pcall(function() emu.setInput(1, { start = on }) end)

  if fr >= DUMP_FRAME and not done then
    done = true
    dumpMem(emu.memType.snesWorkRam, 0x20000, ROOT .. "wram.bin")
    dumpMem(emu.memType.snesVideoRam, 0x10000, ROOT .. "vram.bin")
    dumpMem(emu.memType.snesCgRam, 0x200, ROOT .. "cgram.bin")

    local png = select(2, pcall(function() return emu.takeScreenshot() end))
    if type(png) == "string" then
      local s = io.open(ROOT .. "screen_dump.png", "wb"); s:write(png); s:close()
    end

    local m = io.open(ROOT .. "dump_meta.txt", "w")
    local st = emu.getState()
    m:write(string.format("frame=%d bgMode=%d\n", fr, st["ppu.bgMode"]))
    for lyr = 0, 3 do
      m:write(string.format("BG%d chrAddr(word)=$%04X tilemapAddr(word)=$%04X\n",
        lyr + 1, st["ppu.layers[" .. lyr .. "].chrAddress"], st["ppu.layers[" .. lyr .. "].tilemapAddress"]))
    end
    m:write("dumped wram(128K) vram(64K) cgram(512)\n")
    m:close()
    emu.stop(0)
  end
end

emu.addEventCallback(onFrame, emu.eventType.endFrame)
