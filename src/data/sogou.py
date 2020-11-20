file = open('./Sogou0019.txt','r')
lines = file.readlines()
newfile = open('./sogou.txt','w')
total = len(lines)
for line in lines:
    newline = line.replace(' ', '').replace('<N>', '0')
    newfile.write(newline)
newfile.close()