import sys
sys.path.insert(1,'/home/pi/audioproject/GY-85_Raspberry-Pi/i2clibraries')
from i2c_adxl345 import *
from i2c_itg3205 import *
from i2c_hmc5883l import *
import time
a, b, c = 0, 0, 0
adxl345 = i2c_adxl345(1)
adxl345.setdatarate(0x0F)
itg3205 = i2c_itg3205(1)
hmc5883l = i2c_hmc5883l(1)
hmc5883l.setContinuousMode()
hmc5883l.setDeclination(3, 5)
accwriter = open('acc.txt', 'w')
gyrowriter = open('gyro.txt', 'w')
compasswriter = open('compass.txt', 'w')
time_start = time.time()
for i in range(10000):
    if ( a % 200 == 0):
        (x, y, z) = hmc5883l.getAxes()
        compasswriter.write(str(x) + ' ' + str(y) + ' ' + str(z) + '\n')
        c = c + 1
    itgready, dataready = itg3205.getInterruptStatus()
    if adxl345.getInterruptStatus() & dataready:
        (x1, y1, z1) = adxl345.getRawAxes()
        (x2, y2, z2) = itg3205.getDegPerSecAxes()
        accwriter.write(str(x1) + ' ' + str(y1) + ' ' + str(z1) + '\n')
        gyrowriter.write(str(x2) + ' ' + str(y2) + ' ' + str(z2) + '\n')
        a = a + 1
        b = b + 1
    elif adxl345.getInterruptStatus():
        (x1, y1, z1) = adxl345.getRawAxes()
        accwriter.write(str(x1) + ' ' + str(y1) + ' ' + str(z1) + '\n')
        a = a + 1
    elif dataready:
        (x2, y2, z2) = itg3205.getDegPerSecAxes()
        gyrowriter.write(str(x2) + ' ' + str(y2) + ' ' + str(z2) + '\n')
        b = b + 1
    else:
        pass
time_pass = time.time() - time_start
print(a/time_pass, b/time_pass, c/time_pass)
