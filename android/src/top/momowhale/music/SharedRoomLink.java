package top.momowhale.music;

import java.net.URI;
import java.net.URLDecoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Parses only an explicitly shared link; never reads the clipboard. */
public final class SharedRoomLink {
 public static String parse(String text){
  if(text==null||text.length()>8192)throw new IllegalArgumentException();
  try{
   Matcher m=Pattern.compile("(?<![A-Za-z0-9_./?=&%:-])https://h5\\.kugou\\.com/sharepage/v-96be9ea4/index\\.html\\?[^\\s<>\"，。]+").matcher(text);
   if(!m.find())throw new IllegalArgumentException();String value=m.group();if(m.find())throw new IllegalArgumentException();
   URI u=new URI(value);
   if(!"https".equals(u.getScheme())||!"h5.kugou.com".equals(u.getRawAuthority())||!"/sharepage/v-96be9ea4/index.html".equals(u.getPath())||u.getFragment()!=null)throw new IllegalArgumentException();
   String code=null,eid=null;
   for(String part:u.getRawQuery().split("&")){
    String[] pair=part.split("=",2);if(pair.length!=2)continue;
    String key=URLDecoder.decode(pair[0],"UTF-8"),valuePart=URLDecoder.decode(pair[1],"UTF-8");
    if("code".equals(key)){if(code!=null||!valuePart.matches("[0-9a-fA-F]{32}"))throw new IllegalArgumentException();code=valuePart;}
    if("eid".equals(key)){if(eid!=null||!valuePart.matches("[0-9]{1,32}"))throw new IllegalArgumentException();eid=valuePart;}
   }
   if(code==null)throw new IllegalArgumentException();
   return "https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code="+code+(eid==null?"":"&eid="+eid);
  }catch(Exception e){throw new IllegalArgumentException("unsupported_invite");}
 }
}
