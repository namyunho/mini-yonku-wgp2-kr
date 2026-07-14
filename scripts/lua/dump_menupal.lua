-- dump_menupal.lua : 표시된 메뉴에서 텍스트 타일맵($7E 버퍼 + VRAM)의 팔레트비트 덤프.
--   메뉴 문자열 읽힘 +60프레임(표시 안정)에 $7E:48C0-4920(48엔트리) + 대응 VRAM 읽기.
--   비활성 옵션의 회색처리 타일범위 확인 → 한글 정렬용.
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/menu2/menupal_dump.txt"
local armFrame = nil
emu.addMemoryCallback(function()
  if not armFrame then armFrame = emu.getState()["frameCount"] end
end, emu.callbackType.read, 0xC071B9, 0xC071C0, emu.cpuType.snes, emu.memType.snesMemory)

local done=false
emu.addEventCallback(function()
  local fr=emu.getState()["frameCount"]
  if armFrame and fr>=armFrame+60 and not done then
    done=true
    local f=io.open(OUT,"w")
    -- $7E:48C0부터 48엔트리(16bit LE) — 렌더러 기록버퍼
    f:write("# $7E tilemap buffer @48C0 (col: tileval palbits)\n")
    for i=0,47 do
      local a=0x7E0000+0x48C0+i*2
      local lo=emu.read(a, emu.memType.snesMemory)
      local hi=emu.read(a+1, emu.memType.snesMemory)
      local v=lo+hi*256
      local pal=(v>>10)&7
      f:write(string.format("col%d $%04X pal=%d\n", i, v, pal))
    end
    f:close()
    emu.stop(0)
  end
  if fr>4000 and not done then done=true; emu.stop(0) end
end, emu.eventType.endFrame)
