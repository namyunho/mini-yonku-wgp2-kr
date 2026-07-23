-- trace_garage_categories.lua
-- 개러지 부품 분류명의 실제 공급 경로를 한 화면에서 판별한다.
-- 실행 후 개러지 부품 화면을 한 번 벗어났다 다시 열고 2초 정도 둔다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/garage_categories/"
os.execute('mkdir -p "' .. ROOT .. '"')

local rows = {}
local seen = {}

local function hex(value, width)
  return string.format("%0" .. width .. "X", value or 0)
end

local function state_line(tag, extra)
  local st = emu.getState()
  return table.concat({
    "f=" .. tostring(st["frameCount"] or 0),
    tag,
    "pc=$" .. hex(st["cpu.k"], 2) .. ":" .. hex(st["cpu.pc"], 4),
    "a=$" .. hex(st["cpu.a"], 4),
    "x=$" .. hex(st["cpu.x"], 4),
    "y=$" .. hex(st["cpu.y"], 4),
    "d=$" .. hex(st["cpu.d"], 4),
    "dbr=$" .. hex(st["cpu.dbr"], 2),
    extra or "",
  }, "\t")
end

local function flush()
  local f = assert(io.open(ROOT .. "trace.txt", "w"))
  for _, row in ipairs(rows) do f:write(row .. "\n") end
  f:close()
end

local function add_once(key, row)
  if seen[key] then return end
  seen[key] = true
  rows[#rows + 1] = row
  flush()
end

-- 개러지 화면 선택값 -> C2 자원표 인덱스와 실제 LZSS 소스.
emu.addMemoryCallback(function()
  local st = emu.getState()
  local screen = emu.read(0x7E712E, emu.memType.snesMemory) & 0xFF
  add_once("screen:" .. screen, state_line("screen-select", "screen=" .. screen))
end, emu.callbackType.exec, 0xC0AEB4, 0xC0AEB4,
    emu.cpuType.snes, emu.memType.snesMemory)

emu.addMemoryCallback(function()
  local st = emu.getState()
  local x = st["cpu.x"] or 0
  local lo = emu.read(0xC20050 + x, emu.memType.snesMemory) & 0xFF
  local hi = emu.read(0xC20051 + x, emu.memType.snesMemory) & 0xFF
  local bank = emu.read(0xC20052 + x, emu.memType.snesMemory) & 0xFF
  local source = "$" .. hex(bank, 2) .. ":" .. hex((hi << 8) | lo, 4)
  add_once("gfx:" .. x, state_line("gfx-source", "source=" .. source))
end, emu.callbackType.exec, 0xC0AF7A, 0xC0AF7A,
    emu.cpuType.snes, emu.memType.snesMemory)

-- SJIS 경로와 직접 타일 경로 중 어느 쪽이 분류명을 쓰는지 판별한다.
for _, address in ipairs({0xC1965E, 0xC19843, 0xC01B4B}) do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local d = st["cpu.d"] or 0
    local cell = emu.read((d + 5) & 0xFFFF, emu.memType.snesMemory) & 0xFF
    local marker = emu.read((d + 6) & 0xFFFF, emu.memType.snesMemory) & 0xFF
    local key = string.format("exec:%06X:%02X:%02X", address, marker, cell)
    add_once(key, state_line("exec-$" .. hex(address, 6),
      "dp05=$" .. hex(cell, 2) .. " dp06=$" .. hex(marker, 2)))
  end, emu.callbackType.exec, address, address,
      emu.cpuType.snes, emu.memType.snesMemory)
end

-- 기존 분류명 문자열 주소가 실제로 읽히는지 확인한다.
emu.addMemoryCallback(function(address, value)
  local st = emu.getState()
  local key = string.format("read:%06X:%02X:%02X%04X", address, value,
    st["cpu.k"] or 0, st["cpu.pc"] or 0)
  add_once(key, state_line("category-rom-read",
    "address=$" .. hex(address, 6) .. " value=$" .. hex(value, 2)))
end, emu.callbackType.read, 0xC0EBE0, 0xC0EC30,
    emu.cpuType.snes, emu.memType.snesMemory)

-- 화면이 열린 뒤의 실제 VRAM/WRAM/스크린샷을 주기적으로 최신 상태로 보존한다.
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

local ticks = 0
emu.addEventCallback(function()
  ticks = ticks + 1
  if ticks % 60 ~= 0 then return end
  write_blob(ROOT .. "vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
  write_blob(ROOT .. "wram.bin", 0x7E0000, 0x20000, emu.memType.snesMemory)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local f = assert(io.open(ROOT .. "screen.png", "wb")); f:write(png); f:close()
  end
end, emu.eventType.endFrame)

flush()
emu.displayMessage("trace", "개러지 분류명 추적 준비 완료")
