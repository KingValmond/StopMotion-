#Import export mechanism for Stopmotion++ with its data-class

class SMData():
    def __init__(self):
        print ""
        #
    
    frames = []
    
    def Clear(self):
        frames = set()
    
    def Save(self, name):
        import json
        data = {}
        #data['key3'] = 'value3'   #example

        data['frames'] = self.frames

        try:
            with open(name+'.smp', 'w') as f:
                json.dump(data, f)
            print "saved project: "+name+'.smp'
        except IOError, e:
            print "Save project data error"
            print e.errno
            print e
    
    