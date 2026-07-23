-- reclean_menu_probe.lua
-- 기존 메뉴4 분석 주소를 전혀 사용하지 않는 원본 ROM 화면 프로브.
-- 현재 화면의 PPU 상태·VRAM·WRAM·스크린샷과 모든 DMA 트리거를 기록한다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/reclean_menu_probe/"
os.execute('mkdir -p "' .. ROOT .. '"')

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local chunk = {}
  for i = 0, size - 1 do
    chunk[#chunk + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #chunk == 4096 then
      f:write(table.concat(chunk))
      chunk = {}
    end
  end
  if #chunk > 0 then f:write(table.concat(chunk)) end
  f:close()
end

local function sorted_state()
  local st = emu.getState()
  local keys = {}
  for k, _ in pairs(st) do keys[#keys + 1] = k end
  table.sort(keys)
  local out = {}
  for _, k in ipairs(keys) do
    out[#out + 1] = string.format("%s=%s", k, tostring(st[k]))
  end
  return table.concat(out, "\n") .. "\n"
end

local function checkpoint(tag)
  local st = emu.getState()
  local frame = st["frameCount"] or 0
  local base = ROOT .. string.format("%s_f%07d", tag, frame)

  local sf = assert(io.open(base .. "_state.txt", "w"))
  sf:write(sorted_state())
  sf:close()

  write_blob(base .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(base .. "_wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)

  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local pf = assert(io.open(base .. "_screen.png", "wb"))
    pf:write(png)
    pf:close()
  end

  emu.displayMessage("reclean", string.format("독립 덤프 %s f=%d", tag, frame))
end

local dma_rows = {}
local function flush_dma()
  local f = assert(io.open(ROOT .. "dma.txt", "w"))
  f:write("# 원본 ROM $420B DMA 전수 기록\n")
  for _, row in ipairs(dma_rows) do f:write(row .. "\n") end
  f:close()
end

emu.addMemoryCallback(function(_, value)
  local st = emu.getState()
  local k = st["cpu.k"] or 0
  local pc = st["cpu.pc"] or 0
  local frame = st["frameCount"] or 0
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local p = "dmaController.channel[" .. ch .. "]."
      local sz = st[p .. "transferSize"] or 0
      if sz == 0 then sz = 65536 end
      dma_rows[#dma_rows + 1] = string.format(
        "f=%-7d caller=$%02X:%04X ch=%d ctrl=$%02X bbus=$21%02X src=$%02X:%04X size=%d vmadd=$%04X",
        frame, k, pc, ch,
        st[p .. "transferMode"] or 0,
        st[p .. "destAddress"] or 0,
        st[p .. "srcBank"] or 0,
        st[p .. "srcAddress"] or 0,
        sz,
        st["ppu.vramAddress"] or 0)
    end
  end
  flush_dma()
end, emu.callbackType.write, 0x420B, 0x420B, emu.cpuType.snes, emu.memType.snesMemory)

local tick = 0
local checkpoints = { [5]="a", [65]="b", [125]="c", [185]="d", [245]="e", [305]="f" }
local live_count = 0
emu.addEventCallback(function()
  tick = tick + 1
  local tag = checkpoints[tick]
  if tag then checkpoint(tag) end
  if tick > 305 and (tick - 305) % 120 == 0 and live_count < 20 then
    live_count = live_count + 1
    checkpoint(string.format("live%02d", live_count))
  end
  if tick == 306 then
    emu.displayMessage("reclean", "라이브 프로브 전환(120프레임 간격)")
  end
end, emu.eventType.endFrame)

emu.displayMessage("reclean", "원본 독립 프로브: 60프레임 간격 6회 덤프")
