#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
int main(int argc, char **argv) {
 @autoreleasepool {
  printf("pid=%d\n",getpid()); fflush(stdout);
  int fd=open("/usr/share/icu/icudt76l.dat",O_RDONLY); int e=errno;
  printf("icu_open=%d errno=%d\n",fd>=0,e); if(fd>=0)close(fd);
  CFLocaleRef loc=CFLocaleCreate(NULL,CFSTR("en_US_POSIX"));
  CFDateFormatterRef fmt=CFDateFormatterCreate(NULL,loc,kCFDateFormatterShortStyle,kCFDateFormatterShortStyle);
  printf("date_formatter=%d\n",fmt!=NULL); if(fmt)CFRelease(fmt); CFRelease(loc); fflush(stdout);
  NSString *root=[NSString stringWithUTF8String:argv[1]];
  NSData *data=[@"fake" dataUsingEncoding:NSUTF8StringEncoding];
  for (NSUInteger flag=0; flag<2; flag++) {
   NSError *err=nil;
   NSString *p=[root stringByAppendingPathComponent:flag?@"atomic.plist":@"direct.plist"];
   BOOL ok=[data writeToFile:p options:flag?NSDataWritingAtomic:0 error:&err];
   printf("write_%s=%d error=%s\n",flag?"atomic":"direct",ok,err?[[err description] UTF8String]:"none"); fflush(stdout);
  }
  NSError *err=nil; NSURL *url=[NSURL fileURLWithPath:[root stringByAppendingPathComponent:@"dictionary.plist"]];
  BOOL ok=[@{@"fake":@YES} writeToURL:url error:&err];
  printf("dictionary=%d error=%s\n",ok,err?[[err description] UTF8String]:"none");
 }
 return 0;
}
