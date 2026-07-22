-- trace_formation_oam.lua
-- 포메이션 선택 라벨의 두 OAM 프레임에서 스프라이트 타일 번호만 회수한다.
-- 포메이션 화면에서 한 항목에 커서를 둔 채 실행하고 3초간 기다린다.

local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/formation_oam/"
os.execute('mkdir -p "' .. ROOT .. '"')

local start_frame = emu.getState()["frameCount"] or 0
local duration = 210

local function write_blob(path, first, size, mem_type)
  local f = assert(io.open(path, "wb"))
  local buffer = {}
  for i = 0, size - 1 do
    buffer[#buffer + 1] = string.char(emu.read(first + i, mem_type) & 0xFF)
  end
  f:write(table.concat(buffer)); f:close()
end

local state_file = assert(io.open(ROOT .. "ppu_state.txt", "w"))
local state = emu.getState()
for key, value in pairs(state) do
  if type(key) == "string" and string.sub(key, 1, 4) == "ppu." then
    state_file:write(key .. "=" .. tostring(value) .. "\n")
  end
end
state_file:close()

write_blob(ROOT .. "vram.bin", 0, 0x10000, emu.memType.snesVideoRam)
write_blob(ROOT .. "cgram.bin", 0, 0x200, emu.memType.snesCgRam)

emu.addEventCallback(function()
  local frame = emu.getState()["frameCount"] or 0
  local elapsed = frame - start_frame
  if elapsed < 0 or elapsed > duration or elapsed % 2 ~= 0 then return end
  local stem = string.format("frame_%03d_f%d", elapsed // 2, frame)
  write_blob(ROOT .. stem .. "_oam.bin", 0, 0x220, emu.memType.snesSpriteRam)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local f = assert(io.open(ROOT .. stem .. ".png", "wb")); f:write(png); f:close()
  end
end, emu.eventType.endFrame)

emu.displayMessage("trace", "현재 항목을 그대로 두고 3초간 기다려 주세요")
