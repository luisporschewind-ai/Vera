#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
int main(int argc,char **argv){
 if(argc<2){puts("native-compiled-ok");return 0;}
 int fd=-1,rc=-1;
 if(!strcmp(argv[1],"read")){fd=open(argv[2],O_RDONLY);rc=fd<0?-1:0;}
 if(!strcmp(argv[1],"write")){fd=open(argv[2],O_WRONLY|O_CREAT|O_TRUNC,0600);rc=fd<0?-1:0;}
 if(!strcmp(argv[1],"connect")){
  fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0){printf("socket errno=%d\n",errno);return 90;}
  struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons(atoi(argv[2]));inet_pton(AF_INET,"127.0.0.1",&a.sin_addr);rc=connect(fd,(struct sockaddr*)&a,sizeof(a));
 }
 int e=rc<0?errno:0;printf("operation=%s result=%d errno=%d\n",argv[1],rc,e);if(fd>=0)close(fd);
 return rc==0?0:(e==EPERM||e==EACCES?13:90);
}
