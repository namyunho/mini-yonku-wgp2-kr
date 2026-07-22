-- trace_formation_select.lua
-- 포메이션 하단 네 항목의 선택용 OBJ 타일과 갱신 소스를 한 번에 추적한다.
-- 포메이션 화면에서 실행한 뒤 SETTING -> EASY SETTING -> TEST RUN -> COURSE를
-- 차례로 선택하고, 각 항목에서 약 1초씩 멈춘다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/formation_select/"
os.execute('mkdir -p "' .. ROOT .. '"')

local trace = assert(io.open(ROOT .. "trace.txt", "w"))
local start_frame = emu.getState()["frameCount"] or 0
local duration = 600
local event_number = 0
local last_signature = ""

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function add(text)
  trace:write(text .. "\n")
  trace:flush()
end

local function read_cpu(address)
  return emu.read(address & 0xFFFFFF, emu.memType.snesMemory) & 0xFF
end

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local buffer = {}
  for i = 0, size - 1 do
    buffer[#buffer + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
    if #buffer == 4096 then f:write(table.concat(buffer)); buffer = {} end
  end
  if #buffer > 0 then f:write(table.concat(buffer)) end
  f:close()
end

local function screenshot(path)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local f = assert(io.open(path, "wb")); f:write(png); f:close()
  end
end

local function obj_signature()
  local rows = {}
  for index = 0, 31 do
    local base = index * 4
    local x = emu.read(base, emu.memType.snesSpriteRam) & 0xFF
    local y = emu.read(base + 1, emu.memType.snesSpriteRam) & 0xFF
    local tile = emu.read(base + 2, emu.memType.snesSpriteRam) & 0xFF
    local attr = emu.read(base + 3, emu.memType.snesSpriteRam) & 0xFF
    local high = emu.read(0x200 + (index // 4), emu.memType.snesSpriteRam)
    local bits = (high >> ((index % 4) * 2)) & 3
    x = x | ((bits & 1) << 8)
    if x >= 256 then x = x - 512 end
    tile = tile | ((attr & 1) << 8)
    if x >= -16 and x < 256 and y >= 68 and y < 104 then
      rows[#rows + 1] = string.format(
        "%d:%d,%d,%03X,%d,%d", index, x, y, tile,
        (attr >> 1) & 7, (bits >> 1) & 1)
    end
  end
  return table.concat(rows, ";")
end

-- 공용 LZSS 해제 진입에서 실제 소스와 복귀주소를 기록한다.
for _, address in ipairs({0xC00D52, 0xC00D91}) do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local d = st["cpu.d"] or 0
    local lo = read_cpu((d + 0x11) & 0xFFFF)
    local hi = read_cpu((d + 0x12) & 0xFFFF)
    local bank = read_cpu((d + 0x13) & 0xFFFF)
    local sp = st["cpu.sp"] or 0
    local ret_lo = read_cpu((sp + 1) & 0xFFFF)
    local ret_hi = read_cpu((sp + 2) & 0xFFFF)
    local ret_bank = read_cpu((sp + 3) & 0xFFFF)
    local ret = (((ret_bank << 16) | (ret_hi << 8) | ret_lo) + 1) & 0xFFFFFF
    add(string.format("f=%d\tlzss\tentry=$%06X\tsource=$%02X:%04X\treturn=$%06X",
      st["frameCount"] or 0, address, bank, (hi << 8) | lo, ret))
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- VRAM DMA는 목적지와 WRAM/ROM 소스를 직접 기록한다.
emu.addMemoryCallback(function(_, value)
  local st = emu.getState()
  for channel = 0, 7 do
    if (value & (1 << channel)) ~= 0 then
      local p = "dmaController.channel[" .. channel .. "]."
      local dest = st[p .. "destAddress"]
      if dest == 0x18 or dest == 0x19 then
        local size = st[p .. "transferSize"] or 0
        if size == 0 then size = 65536 end
        add(string.format("f=%d\tdma\tch=%d\tsrc=$%02X:%04X\tsize=$%04X\tvmadd=$%04X",
          st["frameCount"] or 0, channel, st[p .. "srcBank"] or 0,
          st[p .. "srcAddress"] or 0, size, st["ppu.vramAddress"] or 0))
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B,
    emu.cpuType.snes, emu.memType.snesMemory)

-- 선택 타일 영역의 직접 VRAM 쓰기도 별도 기록한다.
emu.addMemoryCallback(function(address, value)
  local st = emu.getState()
  add(string.format("f=%d\tvram-write\taddress=$%04X\tvalue=$%02X\tpc=$%02X:%04X",
    st["frameCount"] or 0, address, value or 0,
    st["cpu.k"] or 0, st["cpu.pc"] or 0))
end, emu.callbackType.write, 0xE000, 0xEFFF,
    emu.cpuType.snes, emu.memType.snesVideoRam)

write_blob(ROOT .. "wram_start.bin", 0, 0x20000, emu.memType.snesWorkRam)
write_blob(ROOT .. "vram_start.bin", 0, 0x10000, emu.memType.snesVideoRam)

emu.addEventCallback(function()
  local frame = emu.getState()["frameCount"] or 0
  if frame < start_frame or frame > start_frame + duration then return end
  local signature = obj_signature()
  if signature ~= last_signature then
    event_number = event_number + 1
    local stem = string.format("event_%03d_f%d", event_number, frame)
    add(string.format("f=%d\toam-change\t%s\t%s", frame, stem, signature))
    write_blob(ROOT .. stem .. "_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
    write_blob(ROOT .. stem .. "_vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
    screenshot(ROOT .. stem .. ".png")
    last_signature = signature
  end
  if frame == start_frame + duration then
    write_blob(ROOT .. "wram_end.bin", 0, 0x20000, emu.memType.snesWorkRam)
    trace:close()
    emu.displayMessage("trace", "포메이션 네 항목 추적 완료")
  end
end, emu.eventType.endFrame)

add("session-start frame=" .. tostring(start_frame))
emu.displayMessage("trace", "네 항목을 차례로 선택하고 각 1초씩 멈춰 주세요")
