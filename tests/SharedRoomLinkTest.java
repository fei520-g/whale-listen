import top.momowhale.music.SharedRoomLink;
public final class SharedRoomLinkTest {
 public static void main(String[] args){
  String base="https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  if(!SharedRoomLink.parse("来一起听 "+base+"&eid=123&ignored=1").equals(base+"&eid=123"))throw new AssertionError("valid share");
  for(String bad:new String[]{"", "https://evil.example/?url="+base, base+"&code=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",base+"#fragment",base+" "+base,base+"&eid=../bad"}){
   try{SharedRoomLink.parse(bad);throw new AssertionError("accepted bad link");}catch(IllegalArgumentException expected){}
  }
  System.out.println("PASS shared invite validation");
 }
}
