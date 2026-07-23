-- trace_menu_extra.lua
-- 추가 소형 메뉴(확인창/다음 LV/레이스 일시정지)의 실제 렌더 소스를 찾는다.
-- 화면 조작은 하지 않으며, 사용자가 목표 화면에 들어갈 때의 렌더 호출·DMA와
-- 현재 PPU/VRAM/WRAM/OAM/CGRAM을 tmp/menu_extra_trace/에 기록한다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/menu_extra_trace/"
os.execute('mkdir -p "' .. ROOT .. '"')

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function read8(address)
  return emu.read(address, emu.memType.snesMemory) & 0xFF
end

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local bytes = {}
  for i = 0, size - 1 do
    bytes[#bytes + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #bytes == 4096 then
      f:write(table.concat(bytes))
      bytes = {}
    end
  end
  if #bytes > 0 then f:write(table.concat(bytes)) end
  f:close()
end

local direct = assert(io.open(ROOT .. "direct_calls.tsv", "w"))
direct:write("frame\tcaller\tbase\tdest\tpointer\tbytes\n")
direct:flush()

local function trace_direct_call()
  local st = emu.getState()
  local sp = st["cpu.sp"] or 0
  local ret_lo = read8((sp + 1) & 0xFFFF)
  local ret_hi = read8((sp + 2) & 0xFFFF)
  local ret_bank = read8((sp + 3) & 0xFFFF)
  local ptr_lo = read8((sp + 4) & 0xFFFF)
  local ptr_hi = read8((sp + 5) & 0xFFFF)
  local ptr_bank = read8((sp + 6) & 0xFFFF)
  local pointer = (ptr_bank << 16) | (ptr_hi << 8) | ptr_lo
  local sample = {}
  for i = 0, 63 do sample[#sample + 1] = hex(read8(pointer + i), 2) end
  direct:write(table.concat({
    tostring(st["frameCount"] or 0),
    hex(ret_bank, 2) .. ":" .. hex(((ret_hi << 8) | ret_lo) + 1, 4),
    hex(st["cpu.a"], 4),
    hex(st["cpu.x"], 4),
    hex(ptr_bank, 2) .. ":" .. hex((ptr_hi << 8) | ptr_lo, 4),
    table.concat(sample, " "),
  }, "\t") .. "\n")
  direct:flush()
end

for _, entry in ipairs({0x801B4B, 0xC01B4B}) do
  emu.addMemoryCallback(trace_direct_call, emu.callbackType.exec,
      entry, entry, emu.cpuType.snes, emu.memType.snesMemory)
end

local dma = assert(io.open(ROOT .. "vram_dma.tsv", "w"))
dma:write("frame\tcaller\tchannel\tsource\tsize\tvmadd\n")
dma:flush()
emu.addMemoryCallback(function(_, mask)
  local st = emu.getState()
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      if (st[p .. "destAddress"] or 0) == 0x18 then
        dma:write(table.concat({
          tostring(st["frameCount"] or 0),
          hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
          tostring(channel),
          hex(st[p .. "srcBank"], 2) .. ":" .. hex(st[p .. "srcAddress"], 4),
          tostring(st[p .. "transferSize"] or 0),
          hex(st["ppu.vramAddress"], 4),
        }, "\t") .. "\n")
        dma:flush()
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

local tilemap = assert(io.open(ROOT .. "tilemap_writes.tsv", "w"))
tilemap:write("frame\taddress\tvalue\tcaller\n")
tilemap:flush()
local tilemap_count = 0
emu.addMemoryCallback(function(address, value)
  if tilemap_count >= 100000 then return end
  tilemap_count = tilemap_count + 1
  local st = emu.getState()
  tilemap:write(table.concat({
    tostring(st["frameCount"] or 0), hex(address, 6), hex(value, 2),
    hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
  }, "\t") .. "\n")
  if tilemap_count % 256 == 0 then tilemap:flush() end
end, emu.callbackType.write, 0x7E4000, 0x7E7FFF,
    emu.cpuType.snes, emu.memType.snesMemory)

local function dump_latest()
  local st = emu.getState()
  local sf = assert(io.open(ROOT .. "live_state.txt", "w"))
  local keys = {}
  for key, _ in pairs(st) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    sf:write(string.format("%s=%s\n", key, tostring(st[key])))
  end
  sf:close()
  write_blob(ROOT .. "live_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. "live_wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)
  write_blob(ROOT .. "live_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
  write_blob(ROOT .. "live_cgram.bin", 0, 0x200, emu.memType.snesCgRam)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local pf = assert(io.open(ROOT .. "live_screen.png", "wb"))
    pf:write(png)
    pf:close()
  end
end

local pause_state = assert(io.open(ROOT .. "race_pause.tsv", "w"))
pause_state:write("frame\tentry\tstate\n")
pause_state:flush()
local pause_dumped = false
local function trace_pause_state(address)
  local st = emu.getState()
  pause_state:write(table.concat({
    tostring(st["frameCount"] or 0), hex(address, 6),
    hex(read8(0x0084) | (read8(0x0085) << 8), 4),
  }, "\t") .. "\n")
  pause_state:flush()
  if not pause_dumped then
    pause_dumped = true
    dump_latest()
  end
end

-- 레이스 Start 입력은 $D0:068E에서 state 8을 설정하고, $D0:153D가
-- 일시정지 메뉴를 그린다. HiROM의 $90 미러도 함께 감시한다.
for _, entry in ipairs({0xD0153D, 0x90153D}) do
  emu.addMemoryCallback(trace_pause_state, emu.callbackType.exec,
      entry, entry, emu.cpuType.snes, emu.memType.snesMemory)
end

local ticks = 0
emu.addEventCallback(function()
  ticks = ticks + 1
  if ticks == 10 or ticks % 120 == 0 then dump_latest() end
end, emu.eventType.endFrame)

-- 이미 목표 화면에 들어와 있거나 일시정지 상태에서 스크립트를 켠 경우도
-- endFrame/프레임 어드밴스를 기다리지 않고 현재 상태를 확보한다.
dump_latest()
emu.displayMessage("menu extra", "trace ready: enter target screen")
